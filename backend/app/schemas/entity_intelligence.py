"""Contract 2 — EntityIntelligenceResult.

Canonical output of the (future) entity-intelligence pipeline: the result of
screening a customer against a sanctions list, OFAC SDN, another watchlist, or
adverse media.

CRITICAL ARCHITECTURAL BOUNDARIES (preserved in Phase 1, enforced in code):

  * ``match_confidence`` is confidence in ENTITY IDENTITY RESOLUTION — how sure
    we are that the external record refers to the SAME entity as the customer.
    It is NOT the customer's risk score. This model deliberately carries no
    risk field.

  * A high name similarity must NEVER, by itself, become ``confirmed_match``.
    Identity has to be corroborated by additional attributes (country, role,
    DOB, organization, etc.). See docs/integration-contracts.md.

The resolution algorithms (deterministic rules, fuzzy / alias / semantic /
contextual matching) and the screening sources themselves are NOT implemented
in Phase 1 — this file defines only the contract shape.
"""

from __future__ import annotations

from pydantic import Field

from app.schemas.common import (
    AwareUTC,
    CanonicalModel,
    EntityMatchDecision,
    NonBlankStr,
    Score,
    utcnow,
)


class EntityIntelligenceResult(CanonicalModel):
    """Canonical result of screening a customer against one entity source."""

    # --- Identity of the result and the customer it concerns ---
    result_id: NonBlankStr = Field(
        ...,
        description="Stable identifier for this screening result (required, non-blank).",
    )
    client_id: NonBlankStr = Field(
        ...,
        description="Canonical customer identifier this result concerns.",
    )

    # --- Provenance of the source that produced the candidate ---
    source_type: NonBlankStr = Field(
        ...,
        description="Category of source, e.g. 'sanctions', 'watchlist', 'adverse_media'.",
    )
    source_name: NonBlankStr = Field(
        ...,
        description="Specific authoritative source, e.g. 'OFAC SDN', 'OpenSanctions'.",
    )

    # --- The match itself ---
    matched_entity_name: str | None = Field(
        default=None,
        description="Name of the matched external entity, if any (None when no match).",
    )
    match_confidence: Score = Field(
        ...,
        description=(
            "Confidence (0-100) in ENTITY IDENTITY RESOLUTION only. "
            "This is NOT the customer's risk score."
        ),
    )
    decision: EntityMatchDecision = Field(
        ...,
        description=(
            "Screening decision. A name match alone is never 'confirmed_match'; "
            "identity must be corroborated by additional attributes."
        ),
    )

    # --- Explainability & traceability ---
    matched_attributes: list[str] = Field(
        default_factory=list,
        description=(
            "Attributes that contributed to the match (e.g. 'name', 'alias', "
            "'dob', 'country', 'role'). Supports downstream explainability."
        ),
    )
    evidence_references: list[str] = Field(
        default_factory=list,
        description=(
            "References to supporting evidence records, enabling downstream "
            "traceability of every material finding to a verifiable source."
        ),
    )

    evaluated_at: AwareUTC = Field(
        default_factory=utcnow,
        description="When this result was evaluated (tz-aware UTC).",
    )
