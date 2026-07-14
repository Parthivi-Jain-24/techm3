"""Stage 2 — LLM-synthesised investigation findings.

Pipeline position:
    EntitySignal + TransactionSignal → **InvestigationFinding** → DebateArgument
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.common import ConfidenceLevel, EvidenceItem, RiskLevel


class RiskIndicator(BaseModel):
    indicator: str = Field(..., description="Short label, e.g. 'FATF high-risk jurisdiction'")
    severity: RiskLevel = RiskLevel.MEDIUM
    detail: str = Field("", description="Expanded explanation")


class InvestigationFinding(BaseModel):
    """Output of the investigator agent — one finding per client per run."""

    client_id: int
    summary: str = Field(
        ...,
        description="Plain-English synopsis of what was found",
    )
    risk_indicators: list[RiskIndicator] = Field(
        default_factory=list,
        description="Discrete risk signals identified during analysis",
    )
    evidence: list[EvidenceItem] = Field(
        default_factory=list,
        description="Claims with provenance that support the summary",
    )
    confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM
