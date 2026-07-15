"""Phase 1 tests for the two integration-boundary contracts.

These lock in the *shape and invariants* of NormalizedKYCEntity and
EntityIntelligenceResult — not any business logic (which does not exist yet).
"""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.schemas.entity_intelligence import EntityIntelligenceResult
from app.schemas.kyc import NormalizedKYCEntity


# --------------------------------------------------------------------------- #
# NormalizedKYCEntity
# --------------------------------------------------------------------------- #
def _valid_kyc(**overrides) -> NormalizedKYCEntity:
    data = dict(
        client_id="CLIENT-001",
        client_name="ABC Technologies Ltd",
        client_type="corporate",
        country="IN",
        sector="technology",
        sector_risk="high",  # ordinal category (Phase 2 schema change)
    )
    data.update(overrides)
    return NormalizedKYCEntity(**data)


def test_kyc_valid_creation() -> None:
    entity = _valid_kyc()
    assert entity.client_id == "CLIENT-001"
    assert entity.pep_flag is False
    assert entity.sanctions_flag is False
    assert entity.fatf_country_flag is False


def test_kyc_missing_client_id_is_rejected() -> None:
    with pytest.raises(ValidationError):
        NormalizedKYCEntity(
            client_name="ABC Technologies Ltd",
            client_type="corporate",
            country="IN",
            sector="technology",
            sector_risk="high",
        )


def test_kyc_blank_client_id_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _valid_kyc(client_id="   ")


def test_kyc_blank_client_name_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _valid_kyc(client_name="")


def test_kyc_aliases_defaults_to_empty_list() -> None:
    assert _valid_kyc().aliases == []


def test_kyc_aliases_default_not_shared_between_instances() -> None:
    a = _valid_kyc()
    b = _valid_kyc()
    a.aliases.append("ABC Tech")
    assert b.aliases == []  # mutable default must not be shared


def test_kyc_naive_timestamp_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _valid_kyc(created_at=datetime(2026, 1, 1, 12, 0, 0))  # tz-naive


def test_kyc_aware_timestamp_is_accepted() -> None:
    entity = _valid_kyc(created_at=datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc))
    assert entity.created_at.tzinfo is not None


def test_kyc_sector_risk_accepts_documented_categories() -> None:
    for level in ("low", "medium", "high"):
        assert _valid_kyc(sector_risk=level).sector_risk.value == level


def test_kyc_sector_risk_rejects_unknown_category() -> None:
    # Phase 2: sector_risk is an ordinal enum (low/medium/high), not 0-100.
    with pytest.raises(ValidationError):
        _valid_kyc(sector_risk="42")
    with pytest.raises(ValidationError):
        _valid_kyc(sector_risk="extreme")


def test_kyc_rejects_unexpected_fields() -> None:
    with pytest.raises(ValidationError):
        _valid_kyc(ssn="123-45-6789")  # canonical contracts forbid extras


def test_kyc_serializes_to_json_compatible() -> None:
    dumped = _valid_kyc().model_dump(mode="json")
    assert dumped["client_id"] == "CLIENT-001"
    assert isinstance(dumped["created_at"], str)  # tz-aware ISO string
    assert dumped["aliases"] == []


# --------------------------------------------------------------------------- #
# EntityIntelligenceResult
# --------------------------------------------------------------------------- #
def _valid_result(**overrides) -> EntityIntelligenceResult:
    data = dict(
        result_id="RES-001",
        client_id="CLIENT-001",
        source_type="sanctions",
        source_name="OFAC SDN",
        matched_entity_name="Rahul Sharma",
        match_confidence=55.0,
        decision="needs_review",
    )
    data.update(overrides)
    return EntityIntelligenceResult(**data)


def test_result_valid_creation() -> None:
    result = _valid_result()
    assert result.client_id == "CLIENT-001"
    assert result.match_confidence == 55.0
    assert result.matched_attributes == []
    assert result.evidence_references == []


def test_result_match_confidence_below_zero_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _valid_result(match_confidence=-0.1)


def test_result_match_confidence_above_hundred_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _valid_result(match_confidence=100.1)


def test_result_confidence_boundaries_accepted() -> None:
    assert _valid_result(match_confidence=0).match_confidence == 0
    assert _valid_result(match_confidence=100).match_confidence == 100


def test_result_likely_false_positive_is_valid_decision() -> None:
    assert _valid_result(decision="likely_false_positive").decision.value == (
        "likely_false_positive"
    )


def test_result_all_documented_decisions_are_valid() -> None:
    for decision in (
        "confirmed_match",
        "likely_match",
        "needs_review",
        "likely_false_positive",
        "no_match",
    ):
        assert _valid_result(decision=decision).decision.value == decision


def test_result_does_not_model_confidence_as_customer_risk() -> None:
    # Architectural boundary: match confidence is identity-resolution confidence,
    # NOT customer risk. The contract must carry no risk-scoring field.
    fields = set(EntityIntelligenceResult.model_fields)
    assert "match_confidence" in fields
    assert not any("risk" in name for name in fields)


def test_result_rejects_unexpected_fields() -> None:
    with pytest.raises(ValidationError):
        _valid_result(customer_risk_score=90)


def test_result_serializes_to_json_compatible() -> None:
    dumped = _valid_result().model_dump(mode="json")
    assert dumped["decision"] == "needs_review"
    assert dumped["match_confidence"] == 55.0
    assert isinstance(dumped["evaluated_at"], str)


def test_client_id_is_canonical_link_across_contracts() -> None:
    # Both contracts key off the same canonical identifier.
    kyc = _valid_kyc(client_id="ACME-42")
    result = _valid_result(client_id="ACME-42")
    assert kyc.client_id == result.client_id
