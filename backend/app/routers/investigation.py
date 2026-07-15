"""API routes for autonomous investigation.

Endpoints
---------
GET  /api/v1/clients                     — client list for the frontend dropdown
POST /api/v1/investigate/{client_id}     — run the full pipeline, return combined result
GET  /api/v1/investigate/{client_id}/status — check cached result or running state
POST /api/v1/investigate                 — legacy alert-based stub (kept for compat)
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.data_loaders import get_client_profile, list_all_client_ids
from app.schemas.investigation import InvestigationRequest, InvestigationResult
from app.services.investigation_service import run_investigation

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["investigation"])

# ── In-memory results cache ────────────────────────────────────────
# Single-process dev server — no need for Redis/DB yet.
# Keys are client_ids; values are completed PipelineResults.
_results_cache: dict[int, Any] = {}
_running: set[int] = set()


# ── Response models ────────────────────────────────────────────────

class ClientSummary(BaseModel):
    """Lightweight client record for the frontend dropdown."""

    client_id: int
    client_name: str
    country: str
    sector: str
    sector_risk: str
    pep_flag: bool = False
    sanctions_flag: bool = False
    fatf_country_flag: bool = False


class ClientListResponse(BaseModel):
    total: int
    clients: list[ClientSummary]


class PipelineStatusResponse(BaseModel):
    """Wrapper for the GET /status endpoint."""

    client_id: int
    status: str = Field(
        ...,
        description="not_started | running | completed | error",
    )
    result: Optional[Any] = None
    error: Optional[str] = None


# ── GET /clients ───────────────────────────────────────────────────

@router.get("/clients", response_model=ClientListResponse)
async def list_clients():
    """Return every client_id + name from the KYC dataset.

    Designed for a frontend dropdown / search box so the user can
    pick a client to investigate.
    """
    all_ids = list_all_client_ids()
    summaries: list[ClientSummary] = []

    for cid in all_ids:
        profile = get_client_profile(cid)
        if profile is None:
            continue
        summaries.append(ClientSummary(
            client_id=cid,
            client_name=profile.get("client_name", ""),
            country=profile.get("country", ""),
            sector=profile.get("sector", ""),
            sector_risk=profile.get("sector_risk", ""),
            pep_flag=bool(profile.get("pep_flag", 0)),
            sanctions_flag=bool(profile.get("sanctions_flag", 0)),
            fatf_country_flag=bool(profile.get("fatf_country_flag", 0)),
        ))

    return ClientListResponse(total=len(summaries), clients=summaries)


# ── POST /investigate/{client_id} ──────────────────────────────────

@router.post(
    "/investigate/{client_id}",
    summary="Run full investigation pipeline",
)
async def investigate_client(client_id: int):
    """Execute the full pipeline for *client_id* and return the
    combined ``PipelineResult`` with all intermediate outputs.

    The result is cached so ``GET .../status`` can return it later
    without re-running the pipeline.
    """
    # Guard: client must exist
    profile = get_client_profile(client_id)
    if profile is None:
        raise HTTPException(
            status_code=404,
            detail=f"No KYC profile found for client_id={client_id}",
        )

    # Guard: don't allow duplicate concurrent runs for the same client
    if client_id in _running:
        raise HTTPException(
            status_code=409,
            detail=f"Pipeline already running for client_id={client_id}",
        )

    _running.add(client_id)
    try:
        from app.services.orchestrator import run_pipeline

        result = await run_pipeline(client_id)
        _results_cache[client_id] = result
        return result

    except Exception:
        logger.exception(
            "Pipeline failed for client_id=%d", client_id,
        )
        # Build a minimal error PipelineResult so the caller always
        # gets the same response shape.
        raise HTTPException(
            status_code=502,
            detail=f"Pipeline failed for client_id={client_id}. Check server logs.",
        )
    finally:
        _running.discard(client_id)


# ── GET /investigate/{client_id}/status ────────────────────────────

@router.get(
    "/investigate/{client_id}/status",
    response_model=PipelineStatusResponse,
    summary="Check pipeline result / running state",
)
async def investigate_status(client_id: int):
    """Return the cached pipeline result if the client has already
    been investigated, or a status indicator if not.

    Possible ``status`` values:

    - ``not_started`` — no pipeline has been run for this client.
    - ``running``     — a pipeline is currently in progress.
    - ``completed``   — finished; ``result`` contains the full
      ``PipelineResult``.
    - ``error``       — the last run failed; ``result`` may contain
      a partial ``PipelineResult`` with ``outcome="error"``.
    """
    if client_id in _running:
        return PipelineStatusResponse(
            client_id=client_id,
            status="running",
        )

    cached = _results_cache.get(client_id)
    if cached is None:
        return PipelineStatusResponse(
            client_id=client_id,
            status="not_started",
        )

    status = "error" if str(getattr(cached, "outcome", "")) == "error" else "completed"
    return PipelineStatusResponse(
        client_id=client_id,
        status=status,
        result=cached,
        error=cached.error,
    )


# ── Legacy endpoint (kept for backward compat) ────────────────────

@router.post(
    "/investigate",
    response_model=InvestigationResult,
    summary="[Legacy] Alert-based investigation stub",
    deprecated=True,
)
async def investigate_legacy(req: InvestigationRequest):
    return await run_investigation(req.alert)

