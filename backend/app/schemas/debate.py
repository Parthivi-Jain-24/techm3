"""Stage 3 — Adversarial debate between prosecutor / defender agents.

Pipeline position:
    InvestigationFinding → **DebateArgument / DebateVerdict** → SARDraft
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from app.schemas.common import ConfidenceLevel


class DebatePosition(str, Enum):
    RISK_CONFIRMED = "risk_confirmed"
    FALSE_POSITIVE = "false_positive"


class DebateArgument(BaseModel):
    """A single argument put forward during the debate round."""

    position: DebatePosition
    argument: str = Field(
        ..., description="The substantive claim being made"
    )
    cited_evidence: list[str] = Field(
        default_factory=list,
        description="References to EvidenceItem.source_id values or free-text citations",
    )
    strength: ConfidenceLevel = ConfidenceLevel.MEDIUM


class Verdict(str, Enum):
    ESCALATE_TO_SAR = "escalate_to_sar"
    FURTHER_INVESTIGATION = "further_investigation"
    FALSE_POSITIVE_CLEAR = "false_positive_clear"


class DebateVerdict(BaseModel):
    """Judge agent's ruling after reviewing prosecutor and defender arguments."""

    verdict: Verdict
    reasoning: str = Field(
        ..., description="Step-by-step explanation of how the verdict was reached"
    )
    confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM
    key_deciding_evidence: list[str] = Field(
        default_factory=list,
        description="source_id references that most influenced the verdict",
    )
