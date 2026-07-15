"""Typed models for deterministic field classification."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class DataClass(str, Enum):
    """Sensitivity classification for a canonical field.

    Ordered least -> most sensitive. Deterministic; never decided by an LLM.
    """

    PUBLIC = "public"            # safe to expose broadly
    INTERNAL = "internal"        # business/operational, internal-only, not personal
    PERSONAL = "personal"        # identifies/relates to a person or entity (PII-like)
    SENSITIVE = "sensitive"      # sensitive compliance / profiling attribute
    HIGHLY_SENSITIVE = "highly_sensitive"  # strongest protection (identity/hidden identity)


class MaskStrategy(str, Enum):
    """How a field's value is obscured when a context asks for masking."""

    NONE = "none"                # no masking defined (value shown raw when permitted)
    PSEUDONYMIZE = "pseudonymize"  # keyed HMAC pseudonym (log-safe stable id)
    MASK_IDENTIFIER = "mask_identifier"  # keep a few trailing chars
    MASK_NAME = "mask_name"      # keep initials, mask the rest
    REDACT = "redact"            # replace entirely with a placeholder


class FieldClassification(BaseModel):
    """Static, explicit classification metadata for one canonical field."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    field: str = Field(..., description="Canonical field name.")
    data_class: DataClass = Field(..., description="Sensitivity classification.")
    default_mask: MaskStrategy = Field(
        ..., description="Mask strategy applied when a context masks this field."
    )
    rationale: str = Field(..., description="Why this classification was chosen.")
