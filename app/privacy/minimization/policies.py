"""Per-context field treatments (data minimization + masking policy).

Treatment semantics (this is the masking-vs-minimization distinction in code):
  * RAW  -> field present with its real (JSON-safe) value.
  * MASK -> field present but value obscured (field's default mask strategy).
  * OMIT -> field absent entirely (minimization: the consumer does not need it).

Any field not listed for a context is OMITted (fail-closed), so a newly added
canonical field cannot leak into an existing context until deliberately added.
"""

from __future__ import annotations

from enum import Enum

from app.privacy.contexts import ProcessingContext


class Treatment(str, Enum):
    RAW = "raw"
    MASK = "mask"
    OMIT = "omit"


R, M, O = Treatment.RAW, Treatment.MASK, Treatment.OMIT

# Canonical field order for stable output.
CANONICAL_FIELDS: tuple[str, ...] = (
    "client_id",
    "client_name",
    "client_type",
    "country",
    "sector",
    "sector_risk",
    "pep_flag",
    "sanctions_flag",
    "fatf_country_flag",
    "aliases",
    "created_at",
    "updated_at",
)

CONTEXT_POLICIES: dict[ProcessingContext, dict[str, Treatment]] = {
    # Trusted backend: full canonical record legitimately required.
    ProcessingContext.INTERNAL_PROCESSING: {f: R for f in CANONICAL_FIELDS},

    # Logs: minimal operational info; NO names, aliases, or sensitive flags.
    ProcessingContext.LOGGING: {
        "client_id": M,        # pseudonymized
        "client_type": R,
        "country": R,
        "sector_risk": R,
        # everything else omitted
    },

    # Entity resolution: keep identity-matching fields; drop risk/compliance
    # signals and unrelated context (match confidence != customer risk).
    ProcessingContext.ENTITY_SCREENING: {
        "client_id": R,
        "client_name": R,
        "client_type": R,
        "country": R,
        "aliases": R,
        # sector/flags/timestamps omitted — not needed to resolve identity
    },

    # Authorized reviewer view (RBAC enforced later): full business/compliance
    # context, but direct identity is masked until authorization exists.
    ProcessingContext.HUMAN_REVIEW: {
        "client_id": M,
        "client_name": M,
        "client_type": R,
        "country": R,
        "sector": R,
        "sector_risk": R,
        "pep_flag": R,
        "sanctions_flag": R,
        "fatf_country_flag": R,
        "aliases": M,
        "created_at": R,
        "updated_at": R,
    },

    # Future AI/LLM agents: minimized aggressively. Only coarse, non-identifying
    # context by default; a specific bounded task must request more explicitly.
    ProcessingContext.AGENT_CONTEXT: {
        "client_id": M,        # pseudonymous reference
        "client_type": R,
        "country": R,
        "sector_risk": R,
        # no name, aliases, or compliance flags by default
    },

    # Leaving trusted boundaries: most conservative.
    ProcessingContext.EXTERNAL_RESPONSE: {
        "client_id": M,        # pseudonymous reference only
        "client_type": R,
    },
}
