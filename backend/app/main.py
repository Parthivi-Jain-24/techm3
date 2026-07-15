# SHARED FILE — coordinate changes with all workstreams before modifying.
#
# FastAPI application entrypoint for the Continuous KYC Autonomous Auditor.

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.audit.middleware import AuditContextMiddleware
from app.core.config import settings
from app.core.security import SecurityHeadersMiddleware

# Legacy investigation router support
try:
    from app.routers import investigation
except ImportError:
    investigation = None


app = FastAPI(
    title=settings.app_name
    if hasattr(settings, "app_name")
    else "Continuous KYC Autonomous Auditor",
    description="Multi-agent continuous KYC platform for high-risk corporate accounts.",
    version="0.1.0",
)


# Security headers middleware
app.add_middleware(SecurityHeadersMiddleware)


# Audit context middleware
app.add_middleware(AuditContextMiddleware)


# CORS configuration for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Versioned API routes
if hasattr(settings, "api_v1_prefix"):
    app.include_router(
        api_router,
        prefix=settings.api_v1_prefix,
    )
else:
    app.include_router(api_router)


# Existing investigation routes
if investigation:
    app.include_router(investigation.router)


@app.get("/health", tags=["health"])
async def health_check() -> dict:
    """
    Legacy health endpoint retained for compatibility.

    Canonical health endpoint:
    /api/v1/health/live
    """
    return {
        "status": "ok"
    }