"""Shared Pydantic schemas for the Continuous KYC Autonomous Auditor.

This package re-exports all public schema models used across the application,
including investigation, entity intelligence, KYC ingestion, and shared
canonical types.
"""

# -------------------------------------------------------------------
# Common / Canonical Models
# -------------------------------------------------------------------
from app.schemas.common import (
    AwareUTC,
    CanonicalModel,
    ConfidenceLevel,
    EntityMatchDecision,
    EvidenceItem,
    NonBlankStr,
    RiskLevel,
    Score,
    SourceType,
    utcnow,
)

# -------------------------------------------------------------------
# Investigation Pipeline
# -------------------------------------------------------------------
from app.schemas.signals import EntitySignal, TransactionSignal
from app.schemas.findings import InvestigationFinding, RiskIndicator
from app.schemas.debate import (
    DebateArgument,
    DebatePosition,
    DebateVerdict,
    Verdict,
)
from app.schemas.sar import SARDraft
from app.schemas.investigation import (
    Alert,
    Finding,
    InvestigationRequest,
    InvestigationResult,
)

# -------------------------------------------------------------------
# Entity Intelligence
# -------------------------------------------------------------------
from app.schemas.entity_intelligence import EntityIntelligenceResult

# -------------------------------------------------------------------
# KYC
# -------------------------------------------------------------------
from app.schemas.kyc import (
    NormalizedKYCEntity,
    SectorRiskLevel,
)

__all__ = [
    # Canonical
    "AwareUTC",
    "CanonicalModel",
    "ConfidenceLevel",
    "EntityMatchDecision",
    "EvidenceItem",
    "NonBlankStr",
    "RiskLevel",
    "Score",
    "SourceType",
    "utcnow",

    # Investigation
    "EntitySignal",
    "TransactionSignal",
    "InvestigationFinding",
    "RiskIndicator",
    "DebateArgument",
    "DebatePosition",
    "DebateVerdict",
    "Verdict",
    "SARDraft",
    "Alert",
    "Finding",
    "InvestigationRequest",
    "InvestigationResult",

    # Entity Intelligence
    "EntityIntelligenceResult",

    # KYC
    "NormalizedKYCEntity",
    "SectorRiskLevel",
]