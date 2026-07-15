"""Shared canonical models, enums, and reusable schema components.

This module contains common types used across investigation, ingestion,
entity intelligence, privacy, and risk intelligence.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Annotated

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
)


# ---------------------------------------------------------------------
# Canonical utility types
# ---------------------------------------------------------------------

def utcnow() -> datetime:
    """Return the current UTC timestamp."""
    return datetime.now(timezone.utc)


NonBlankStr = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1),
]

AwareUTC = Annotated[
    datetime,
    AwareDatetime,
]

Score = Annotated[
    float,
    Field(ge=0, le=100),
]


# ---------------------------------------------------------------------
# Canonical enums
# ---------------------------------------------------------------------

class EntityMatchDecision(str, Enum):
    CONFIRMED_MATCH = "confirmed_match"
    LIKELY_MATCH = "likely_match"
    NEEDS_REVIEW = "needs_review"
    LIKELY_FALSE_POSITIVE = "likely_false_positive"
    NO_MATCH = "no_match"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ConfidenceLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class SourceType(str, Enum):
    KYC_PROFILE = "kyc_profile"
    TRANSACTION = "transaction"
    SANCTIONS_LIST = "sanctions_list"
    GDPR = "gdpr"
    PEP_REGISTRY = "pep_registry"
    OPEN_SOURCE = "open_source"
    LLM_ANALYSIS = "llm_analysis"


# ---------------------------------------------------------------------
# Base model
# ---------------------------------------------------------------------

class CanonicalModel(BaseModel):
    """Base model shared across integration-boundary schemas."""

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        str_strip_whitespace=True,
    )


# ---------------------------------------------------------------------
# Investigation schema
# ---------------------------------------------------------------------

class EvidenceItem(BaseModel):
    """Evidence supporting an investigation finding."""

    claim: str = Field(
        ...,
        description="Factual assertion this evidence supports",
    )

    source_type: SourceType

    source_id: str = Field(
        ...,
        description="Identifier such as filename, article ID, transaction ID, etc.",
    )

    confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM