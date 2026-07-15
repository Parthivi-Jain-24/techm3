"""Orchestrate an autonomous investigation for a given alert."""

from __future__ import annotations

from app.schemas.investigation import (
    Alert,
    Finding,
    InvestigationResult,
    RiskLevel,
)
from app.data_loaders import get_client_profile, get_client_transactions


async def run_investigation(alert: Alert) -> InvestigationResult:
    findings: list[Finding] = []

    # client_id is passed as a string from the API; coerce to int for lookup
    try:
        cid = int(alert.customer_id)
    except (ValueError, TypeError):
        cid = None

    if cid is not None:
        profile = get_client_profile(cid)
        if profile:
            findings.append(Finding(
                source="customer_profile",
                detail=f"Profile loaded for client {cid}: {profile.get('client_name', 'unknown')}",
                risk_contribution=RiskLevel.LOW,
            ))

        txns = get_client_transactions(cid)
        if txns:
            findings.append(Finding(
                source="transactions",
                detail=f"Found {len(txns)} transactions linked to client {cid}",
                risk_contribution=RiskLevel.LOW,
            ))

    # TODO: integrate LLM agent for deeper analysis
    return InvestigationResult(
        alert_id=alert.alert_id,
        customer_id=alert.customer_id,
        summary="Investigation stub — agent integration pending",
        findings=findings,
        recommended_action="manual_review",
        overall_risk=alert.risk_level,
    )
