# SHARED FILE — coordinate changes with all workstreams before modifying.
#
# FastAPI application entrypoint. Phase 1 wires versioned routing and a
# truthful liveness probe only — no business logic.

from fastapi import FastAPI

from app.api.v1.router import api_router
from app.audit.middleware import AuditContextMiddleware
from app.core.config import settings
from app.core.security import SecurityHeadersMiddleware

app = FastAPI(
    title=settings.app_name,
    description="Multi-agent continuous KYC platform for high-risk corporate accounts.",
    version="0.0.1",
)

# Conservative security headers on every response (no CORS — not required).
app.add_middleware(SecurityHeadersMiddleware)
# Audit context (Phase 9): request-ID correlation + request.completed audit
# event. Added AFTER SecurityHeadersMiddleware so it becomes the OUTERMOST
# middleware (Starlette wraps newest-added middleware outermost) — its
# contextvar must be set before anything downstream (including auth/RBAC/
# ingestion/encryption code with no access to the Request object) runs, and
# it must see the final response status set by everything inside it. See
# docs/audit-logging.md "Middleware behavior".
app.add_middleware(AuditContextMiddleware)

# Versioned API (e.g. /api/v1/health/live).
app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.get("/health", tags=["health"])
def health_check() -> dict:
    # Legacy unversioned root check, retained for backwards compatibility.
    # The canonical Phase 1 liveness probe is GET {api_v1_prefix}/health/live.
    return {"status": "ok"}
