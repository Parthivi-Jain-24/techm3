"""API-layer models for investigation requests and responses.

These wrap the pipeline schemas for the REST API.  The internal pipeline
stages (signals → findings → debate → SAR) live in their own modules.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.common import RiskLevel


class Alert(BaseModel):
    """An incoming alert that triggers an autonomous investigation."""

    alert_id: str
    customer_id: str
    alert_type: str
    description: str = ""
    risk_level: RiskLevel = RiskLevel.MEDIUM


class InvestigationRequest(BaseModel):
    alert: Alert


class Finding(BaseModel):
    source: str = Field(..., description="Which data source or tool produced this finding")
    detail: str
    risk_contribution: RiskLevel = RiskLevel.LOW


class InvestigationResult(BaseModel):
    alert_id: str
    customer_id: str
    summary: str = ""
    findings: list[Finding] = []
    recommended_action: str = ""
    overall_risk: RiskLevel = RiskLevel.MEDIUM
