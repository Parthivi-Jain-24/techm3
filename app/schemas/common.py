# SHARED FILE — coordinate changes with all workstreams before modifying.
#
# Shared building blocks for the canonical integration-boundary contracts.
# Cross-module data contracts are documented in docs/integration-contracts.md.
#
# Phase 1 scope: only the reusable types below and the two contracts that my
# pipeline owns (NormalizedKYCEntity, EntityIntelligenceResult). No business
# logic lives here.

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Annotated

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints


def utcnow() -> datetime:
    """Timezone-aware current time in UTC.

    Used as the default factory for canonical timestamps so that every record
    carries an unambiguous, tz-aware instant (see ``AwareUTC``).
    """
    return datetime.now(timezone.utc)


# A non-blank string: leading/trailing whitespace is stripped and the result
# must contain at least one character. Guards required identifiers such as
# ``client_id`` against empty or whitespace-only values.
NonBlankStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]

# A timezone-aware datetime. Naive (tz-less) datetimes are rejected at
# validation time — canonical records must never carry an ambiguous timestamp.
AwareUTC = Annotated[datetime, AwareDatetime]

# A score on the documented canonical 0-100 scale (inclusive).
#
# IMPORTANT: a "score" here is a generic bounded measure. When used for
# ``match_confidence`` it expresses confidence in ENTITY IDENTITY RESOLUTION,
# which is deliberately NOT the same thing as a customer's risk score.
Score = Annotated[float, Field(ge=0, le=100)]


class EntityMatchDecision(str, Enum):
    """Screening decision for an entity-intelligence result.

    A name match ALONE must never yield ``CONFIRMED_MATCH``; identity must be
    corroborated by additional attributes. The resolution algorithms that
    produce these decisions are NOT implemented in Phase 1.
    """

    CONFIRMED_MATCH = "confirmed_match"
    LIKELY_MATCH = "likely_match"
    NEEDS_REVIEW = "needs_review"
    LIKELY_FALSE_POSITIVE = "likely_false_positive"
    NO_MATCH = "no_match"


class CanonicalModel(BaseModel):
    """Base class for canonical integration-boundary contracts.

    - ``extra="forbid"``: unexpected fields are rejected, so a contract change
      by one workstream cannot silently leak undeclared data to another.
    - ``validate_assignment``: attribute writes are re-validated.
    - JSON uses snake_case field names (the wire convention for the backend).
    """

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        str_strip_whitespace=True,
    )
