"""Processing contexts — WHY data is being used.

Masking and minimization are context-dependent: the same canonical field may be
exposed raw in one context, masked in another, and omitted in a third. These are
engineering boundaries; access-control ENFORCEMENT (who may request which
context) is Phase 4 (authentication/RBAC) and is NOT implemented here.
"""

from __future__ import annotations

from enum import Enum


class ProcessingContext(str, Enum):
    """The purpose for which a KYC representation is being produced."""

    # Trusted backend logic that legitimately needs the full canonical record.
    INTERNAL_PROCESSING = "internal_processing"
    # Application / diagnostic logs. Minimal, no direct identity.
    LOGGING = "logging"
    # Sanctions / watchlist / entity-resolution. Keeps identity-matching fields.
    ENTITY_SCREENING = "entity_screening"
    # Future authorized human reviewer view (RBAC enforced later).
    HUMAN_REVIEW = "human_review"
    # Future policy-controlled AI/LLM agents. Minimized aggressively.
    AGENT_CONTEXT = "agent_context"
    # Data leaving trusted internal boundaries. Conservative by default.
    EXTERNAL_RESPONSE = "external_response"
