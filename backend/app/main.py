from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_v1_router
from app.core.config import settings
from app.core.errors import validation_exception_handler
from app.core.logging_config import setup_logging
from app.core.sentry import init_sentry


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: configure logging and error reporting
    setup_logging()
    init_sentry()
    yield


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


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "version": settings.VERSION}
