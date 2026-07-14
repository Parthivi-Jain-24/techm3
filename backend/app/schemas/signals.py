"""Stage 1 — Screening signals produced by data loaders + fuzzy matching.

Pipeline position:
    Data loaders → **EntitySignal / TransactionSignal** → InvestigationFinding
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.common import ConfidenceLevel


# ── Sanctions / PEP screening ──────────────────────────────────────

class EntitySignal(BaseModel):
    """A potential match between a KYC client and a sanctions/PEP list entry."""

    client_id: int
    matched_entity: str = Field(
        ..., description="Name as it appears on the matched list"
    )
    confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM
    matched_list: str = Field(
        ...,
        description="Source list, e.g. 'OFAC_SDN', 'OpenSanctions'",
    )
    disambiguation_reason: str = Field(
        "",
        description=(
            "Why this match is believed to be (or not be) the same person. "
            "Empty when not yet disambiguated."
        ),
    )


# ── Transaction screening ──────────────────────────────────────────

class TransactionSignal(BaseModel):
    """A single flagged transaction from the AML transaction data."""

    client_id: int
    transaction_id: str = Field(
        ...,
        description="Composite key: Date|Time|Sender_account|Receiver_account",
    )
    laundering_type: str = Field(
        ..., description="Value from SAML-D Laundering_type column"
    )
    is_laundering: bool
    amount: float
    date: str = Field(..., description="YYYY-MM-DD from the Date column")
