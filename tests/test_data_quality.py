"""Phase 3 tests: record-level data-quality assessment (governance layer)."""

from __future__ import annotations

from datetime import datetime, timezone

from app.privacy.quality import (
    QualityIssueCode,
    RecordQualityAssessment,
    assess_record_quality,
)
from app.schemas.kyc import NormalizedKYCEntity


def _entity(**overrides) -> NormalizedKYCEntity:
    data = dict(
        client_id="123456",
        client_name="Acme Corp",
        client_type="Corporate",
        country="IN",
        sector="Tech",
        sector_risk="high",
        aliases=["Acme"],
    )
    data.update(overrides)
    return NormalizedKYCEntity(**data)


# --- 2. deterministic assessment ----------------------------------------- #
def test_valid_entity_assessment_is_deterministic() -> None:
    a = assess_record_quality(_entity())
    b = assess_record_quality(_entity())
    assert a.data_quality_score == b.data_quality_score == 100.0
    assert a.completeness_ratio == b.completeness_ratio == 1.0
    assert a.issues == b.issues == []
    assert a.client_ref == "****56"  # masked, no raw id


# --- 3. score bounds ------------------------------------------------------ #
def test_score_within_bounds_even_with_issues() -> None:
    e = _entity(country="ZZZ")  # invalid country -> low-severity warning
    dup = assess_record_quality(e, known_duplicate=True)
    assert 0 <= dup.data_quality_score <= 100
    codes = {i.issue_code for i in dup.issues}
    assert QualityIssueCode.DUPLICATE_IDENTIFIER in codes
    assert QualityIssueCode.NORMALIZATION_WARNING in codes


def test_inconsistent_timestamps_flagged() -> None:
    e = _entity(
        created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    codes = {i.issue_code for i in assess_record_quality(e).issues}
    assert QualityIssueCode.INCONSISTENT_VALUE in codes


# --- 4. data quality is NOT customer risk -------------------------------- #
def test_quality_score_is_independent_of_risk_flags() -> None:
    low_risk = assess_record_quality(_entity(pep_flag=False, sanctions_flag=False))
    high_risk = assess_record_quality(_entity(pep_flag=True, sanctions_flag=True))
    # A high-risk customer can still have a perfect-quality record.
    assert low_risk.data_quality_score == high_risk.data_quality_score == 100.0


def test_assessment_has_no_risk_field() -> None:
    fields = set(RecordQualityAssessment.model_fields)
    assert not any("risk" in f for f in fields)


# --- 5. separate from match confidence ----------------------------------- #
def test_assessment_has_no_match_confidence_field() -> None:
    fields = set(RecordQualityAssessment.model_fields)
    assert not any("confidence" in f or "match" in f for f in fields)


# --- 6. issues don't expose raw records ---------------------------------- #
def test_quality_issue_carries_no_raw_pii() -> None:
    e = _entity(client_name="Very Secret Name", country="ZZZ")
    for issue in assess_record_quality(e, known_duplicate=True).issues:
        assert set(type(issue).model_fields) == {"field", "issue_code", "severity", "message"}
        assert "Very Secret Name" not in issue.message
        assert "123456" not in issue.message
