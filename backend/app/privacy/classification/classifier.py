"""Explicit, deterministic classification of the actual NormalizedKYCEntity fields.

Classifications are hand-authored (never LLM-decided) and justified per field.
Unknown fields FAIL CLOSED: they are treated as HIGHLY_SENSITIVE + REDACT, never
PUBLIC, so a newly added field cannot leak before it is deliberately classified.
"""

from __future__ import annotations

from app.privacy.classification.models import (
    DataClass,
    FieldClassification,
    MaskStrategy,
)

# Explicit per-field classifications for every current canonical field.
_FIELDS: tuple[FieldClassification, ...] = (
    FieldClassification(
        field="client_id",
        data_class=DataClass.INTERNAL,
        default_mask=MaskStrategy.PSEUDONYMIZE,
        rationale=(
            "Internal surrogate identifier. Not conventional PII, but the value "
            "space is small/predictable, so it is pseudonymized (keyed HMAC) in "
            "exposure contexts to prevent correlation/guessing."
        ),
    ),
    FieldClassification(
        field="client_name",
        data_class=DataClass.PERSONAL,
        default_mask=MaskStrategy.MASK_NAME,
        rationale=(
            "May be an individual's full name (or an organization's legal name). "
            "Treated as personal by default; masking accounts for client_type "
            "(person vs organization)."
        ),
    ),
    FieldClassification(
        field="client_type",
        data_class=DataClass.INTERNAL,
        default_mask=MaskStrategy.NONE,
        rationale="Business categorization (NGO/FI/Corporate/Individual); not personal.",
    ),
    FieldClassification(
        field="country",
        data_class=DataClass.INTERNAL,
        default_mask=MaskStrategy.NONE,
        rationale="Jurisdiction/geo context; business information, not personal alone.",
    ),
    FieldClassification(
        field="sector",
        data_class=DataClass.INTERNAL,
        default_mask=MaskStrategy.NONE,
        rationale="Industry classification; business information.",
    ),
    FieldClassification(
        field="sector_risk",
        data_class=DataClass.INTERNAL,
        default_mask=MaskStrategy.NONE,
        rationale="Inherent sector-risk band (derived business attribute), not personal.",
    ),
    FieldClassification(
        field="pep_flag",
        data_class=DataClass.SENSITIVE,
        default_mask=MaskStrategy.REDACT,
        rationale="Politically-exposed-person status — a sensitive profiling signal about a person.",
    ),
    FieldClassification(
        field="sanctions_flag",
        data_class=DataClass.SENSITIVE,
        default_mask=MaskStrategy.REDACT,
        rationale="Sanctions-association signal — a sensitive compliance attribute.",
    ),
    FieldClassification(
        field="fatf_country_flag",
        data_class=DataClass.INTERNAL,
        default_mask=MaskStrategy.NONE,
        rationale="Country-level FATF risk flag; a jurisdiction attribute, not personal.",
    ),
    FieldClassification(
        field="aliases",
        data_class=DataClass.HIGHLY_SENSITIVE,
        default_mask=MaskStrategy.MASK_NAME,
        rationale="Alternative names can reveal hidden identities; strongest identity sensitivity.",
    ),
    FieldClassification(
        field="created_at",
        data_class=DataClass.INTERNAL,
        default_mask=MaskStrategy.NONE,
        rationale="Record-management metadata (pipeline timestamp); not personal.",
    ),
    FieldClassification(
        field="updated_at",
        data_class=DataClass.INTERNAL,
        default_mask=MaskStrategy.NONE,
        rationale="Record-management metadata (pipeline timestamp); not personal.",
    ),
)

FIELD_CLASSIFICATIONS: dict[str, FieldClassification] = {fc.field: fc for fc in _FIELDS}


def classify(field: str) -> FieldClassification:
    """Return the classification for a field, failing CLOSED for unknowns.

    Unknown fields are conservatively treated as HIGHLY_SENSITIVE + REDACT so a
    field that was never explicitly classified can never be exposed by default.
    """
    known = FIELD_CLASSIFICATIONS.get(field)
    if known is not None:
        return known
    return FieldClassification(
        field=field,
        data_class=DataClass.HIGHLY_SENSITIVE,
        default_mask=MaskStrategy.REDACT,
        rationale="Unknown/unclassified field — conservative fail-closed default.",
    )
