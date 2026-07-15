"""Phase 3 tests: deterministic field classification."""

from __future__ import annotations

from app.privacy.classification import (
    FIELD_CLASSIFICATIONS,
    DataClass,
    MaskStrategy,
    classify,
)
from app.schemas.kyc import NormalizedKYCEntity


def test_every_canonical_field_has_explicit_classification() -> None:
    for field in NormalizedKYCEntity.model_fields:
        assert field in FIELD_CLASSIFICATIONS, f"{field} not classified"
        fc = FIELD_CLASSIFICATIONS[field]
        assert fc.rationale  # documented reasoning present


def test_classification_is_deterministic() -> None:
    assert classify("client_name") == classify("client_name")
    assert classify("client_name").data_class is DataClass.PERSONAL


def test_unknown_field_fails_closed() -> None:
    fc = classify("passport_number")
    assert fc.data_class is DataClass.HIGHLY_SENSITIVE  # never PUBLIC
    assert fc.default_mask is MaskStrategy.REDACT


def test_no_field_is_public_by_accident() -> None:
    # Nothing in the current schema is safe to expose broadly.
    assert all(fc.data_class is not DataClass.PUBLIC for fc in FIELD_CLASSIFICATIONS.values())


def test_identity_fields_are_protected() -> None:
    assert FIELD_CLASSIFICATIONS["aliases"].data_class is DataClass.HIGHLY_SENSITIVE
    assert FIELD_CLASSIFICATIONS["pep_flag"].data_class is DataClass.SENSITIVE
    assert FIELD_CLASSIFICATIONS["client_id"].default_mask is MaskStrategy.PSEUDONYMIZE
