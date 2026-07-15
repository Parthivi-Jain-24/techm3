"""Schemas package — re-exports every public model."""

# ── Shared ──────────────────────────────────────────────────────────
from app.schemas.common import (
    ConfidenceLevel,
    EvidenceItem,
    RiskLevel,
    SourceType,
)

# ── Stage 1: Screening signals ─────────────────────────────────────
from app.schemas.signals import EntitySignal, TransactionSignal

# ── Stage 2: Investigation findings ────────────────────────────────
from app.schemas.findings import InvestigationFinding, RiskIndicator

# ── Stage 3: Adversarial debate ────────────────────────────────────
from app.schemas.debate import (
    DebateArgument,
    DebatePosition,
    DebateVerdict,
    Verdict,
)

# ── Stage 4: SAR draft ─────────────────────────────────────────────
from app.schemas.sar import SARDraft

# ── API layer ───────────────────────────────────────────────────────
from app.schemas.investigation import (
    Alert,
    Finding,
    InvestigationRequest,
    InvestigationResult,
)

__all__ = [
    # common
    "ConfidenceLevel",
    "EvidenceItem",
    "RiskLevel",
    "SourceType",
    # stage 1
    "EntitySignal",
    "TransactionSignal",
    # stage 2
    "InvestigationFinding",
    "RiskIndicator",
    # stage 3
    "DebateArgument",
    "DebatePosition",
    "DebateVerdict",
    "Verdict",
    # stage 4
    "SARDraft",
    # API
    "Alert",
    "Finding",
    "InvestigationRequest",
    "InvestigationResult",
]
