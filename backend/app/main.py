import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    _APScheduler = AsyncIOScheduler
except ImportError:  # apscheduler not installed — scheduler is a no-op
    _APScheduler = None

from app.api.v1.router import api_v1_router
from app.core.config import settings
from app.core.errors import validation_exception_handler
from app.core.logging_config import setup_logging
from app.core.sentry import init_sentry
from app.services.sweeps import sweep_stale_observations, sweep_evidence_ttl

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: configure logging and error reporting
    setup_logging()
    init_sentry()

    # Ensure tables exist and seed default reviewer
    try:
        from app.db.session import get_engine
        from app.db.seed import seed_default_reviewer
        from app.models.entities import Base
        engine = get_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await seed_default_reviewer()
    except Exception as e:
        logger.warning(f"Database auto-init / reviewer seed warning: {e}")

    # Start background sweep scheduler (APScheduler AsyncIOScheduler)
    scheduler = None
    if _APScheduler is not None:
        scheduler = _APScheduler()
        scheduler.add_job(
            sweep_stale_observations,
            trigger="interval",
            seconds=settings.SWEEP_INTERVAL_SECONDS,
            id="sweep_stale_observations",
            replace_existing=True,
        )
        scheduler.add_job(
            sweep_evidence_ttl,
            trigger="interval",
            seconds=settings.EVIDENCE_TTL_CHECK_INTERVAL_SECONDS,
            id="sweep_evidence_ttl",
            replace_existing=True,
        )
        scheduler.start()
        logger.info(
            "APScheduler started: stale-obs sweep every %ds, evidence-TTL sweep every %ds",
            settings.SWEEP_INTERVAL_SECONDS,
            settings.EVIDENCE_TTL_CHECK_INTERVAL_SECONDS,
        )
    else:
        logger.warning(
            "apscheduler not installed — background sweep jobs are disabled. "
            "Run: pip install 'apscheduler>=3.10'"
        )

    yield

    # Shutdown
    if scheduler is not None:
        scheduler.shutdown(wait=False)
        logger.info("APScheduler stopped.")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    lifespan=lifespan,
)

# Exception handlers
app.add_exception_handler(RequestValidationError, validation_exception_handler)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API routes
app.include_router(api_v1_router)

# Internal sweep-trigger routes (firewall/mesh-protected in production)
from app.api.v1.internal import router as internal_router  # noqa: E402
app.include_router(internal_router, prefix="/v1")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "version": settings.VERSION}
