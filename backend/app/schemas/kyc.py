"""Contract 1 — NormalizedKYCEntity.

Canonical normalized customer profile produced by the secure KYC ingestion
pipeline (Phase 2). This is the entry point of my pipeline; every downstream
contract references the customer via ``client_id``.

Phase 2 change (documented): ``sector_risk`` is an ordinal category
(low/medium/high), not a 0-100 number. The real challenge dataset encodes it as
High/Medium/Low, so representing it numerically would invent false precision.
See docs/integration-contracts.md and docs/kyc-ingestion.md.
"""

from __future__ import annotations

from enum import Enum

from pydantic import Field

from app.schemas.common import (
    AwareUTC,
    CanonicalModel,
    NonBlankStr,
    utcnow,
)


class SectorRiskLevel(str, Enum):
    """Ordinal inherent-sector-risk band.

    An inherent attribute of the customer's sector — NOT the customer's
    computed risk score (a different workstream owns risk scoring).
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class NormalizedKYCEntity(CanonicalModel):
    """Canonical normalized KYC profile.

    ``client_id`` is the canonical customer identifier used across every
    workstream. Sensitive raw identifiers (government IDs, full account
    numbers, etc.) are intentionally NOT part of this contract — data
    minimization is applied before a record leaves ingestion.
    """

    # --- Identity ---
    client_id: NonBlankStr = Field(
        ...,
        description="Canonical customer identifier (required, non-blank).",
    )
    client_name: NonBlankStr = Field(
        ...,
        description="Normalized legal/display name (required, non-blank).",
    )
    client_type: NonBlankStr = Field(
        ...,
        description="Customer type, e.g. 'Corporate', 'Individual', 'NGO'.",
    )

    # --- Jurisdiction & sector ---
    country: NonBlankStr = Field(
        ...,
        description="Primary jurisdiction (e.g. ISO country code).",
    )
    sector: NonBlankStr = Field(
        ...,
        description="Business sector / industry classification.",
    )
    sector_risk: SectorRiskLevel = Field(
        ...,
        description=(
            "Inherent sector risk band (low/medium/high), normalized from the "
            "source dataset's categorical value. Inherent sector attribute, "
            "NOT the customer's computed risk score."
        ),
    )

    # --- Profile signals (clear boolean semantics; default False = 'not flagged') ---
    pep_flag: bool = Field(
        default=False,
        description="True if the customer is a Politically Exposed Person.",
    )
    sanctions_flag: bool = Field(
        default=False,
        description="True if the source profile already carries a sanctions association.",
    )
    fatf_country_flag: bool = Field(
        default=False,
        description="True if the jurisdiction is on an FATF high-risk / monitored list.",
    )

    # --- Known aliases (safe empty-list default; not shared between instances) ---
    aliases: list[str] = Field(
        default_factory=list,
        description="Known alternative names for the entity.",
    )

    # --- Record-management timestamps (tz-aware) ---
    # NOTE: these are set by the ingestion pipeline and describe when THIS
    # normalized record was created/updated in our system. They are NOT the
    # customer's onboarding date or any source-provided timestamp (the source
    # dataset carries none). See docs/kyc-ingestion.md.
    created_at: AwareUTC = Field(
        default_factory=utcnow,
        description="When this normalized record was created by the pipeline (tz-aware UTC).",
    )
    updated_at: AwareUTC = Field(
        default_factory=utcnow,
        description="When this normalized record was last updated by the pipeline (tz-aware UTC).",
    )
