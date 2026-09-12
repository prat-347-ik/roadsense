from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.evidence import router as evidence_router
from app.api.v1.incidents import router as incidents_router
from app.api.v1.observations import router as observations_router

api_v1_router = APIRouter(prefix="/v1")

api_v1_router.include_router(auth_router)
api_v1_router.include_router(observations_router)
api_v1_router.include_router(evidence_router)
api_v1_router.include_router(incidents_router)
