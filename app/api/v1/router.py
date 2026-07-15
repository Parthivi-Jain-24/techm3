# SHARED FILE — coordinate changes with all workstreams before modifying.
#
# Aggregate v1 router. Each workstream registers its own sub-router here.
# Phase 1 wires only the health sub-router (Workstreams A & B).

from fastapi import APIRouter

from app.api.routes.auth import router as auth_router
from app.api.routes.health import router as health_router
from app.api.routes.ingestion import router as ingestion_router
from app.api.routes.security import router as security_router

api_router = APIRouter()

api_router.include_router(health_router, prefix="/health", tags=["health"])
api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(security_router, prefix="/security", tags=["security"])
api_router.include_router(ingestion_router, prefix="/ingestion", tags=["ingestion"])

# Example (future):
# from app.cases.services.router import router as cases_router
# api_router.include_router(cases_router, prefix="/cases", tags=["cases"])
