"""Canonical, shared Pydantic schemas.

Integration-boundary contracts owned by the ingestion + entity-intelligence
pipeline live here (not duplicated under feature modules), per the integration
conventions in docs/integration-contracts.md.
"""

from app.schemas.common import (
    AwareUTC,
    CanonicalModel,
    EntityMatchDecision,
    NonBlankStr,
    Score,
    utcnow,
)
from app.schemas.entity_intelligence import EntityIntelligenceResult
from app.schemas.kyc import NormalizedKYCEntity, SectorRiskLevel

__all__ = [
    "AwareUTC",
    "CanonicalModel",
    "EntityMatchDecision",
    "NonBlankStr",
    "Score",
    "utcnow",
    "NormalizedKYCEntity",
    "SectorRiskLevel",
    "EntityIntelligenceResult",
]
