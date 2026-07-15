"""Health routes.

Phase 1 exposes ONLY a truthful liveness probe. It reports that the API
process is running and able to serve requests — nothing more.

It intentionally does NOT check, and must not claim, the health of:
  - PostgreSQL / any database
  - external APIs
  - sanctions / OFAC / OpenSanctions data sources
  - AI / LLM services

Readiness and dependency checks arrive in later phases, once those
dependencies actually exist.
"""

from fastapi import APIRouter

router = APIRouter()


@router.get("/live", summary="Liveness probe", tags=["health"])
def liveness() -> dict[str, str]:
    """Return a static liveness signal. No dependencies are inspected."""
    return {"status": "alive"}
