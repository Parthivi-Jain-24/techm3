"""Tests for the Part 2 -> Part 3/4 contract adapter (projecttechm.contracts).

Distinct from tests/test_contracts.py, which is Part 1's and pins the *shape* of
NormalizedKYCEntity / EntityIntelligenceResult. This file pins the *translation*
from our internal EvidenceRecord onto that contract.

Four things differ between the two, and each is somewhere a silent bug would
live: score scale, decision vocabulary, identity-vs-risk semantics, and source
provenance.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from projecttechm.contracts import (
    CORROBORATION_FLOOR,
    SCORE_SCALE,
    adverse_media_to_result,
    evidence_to_result,
)
from projecttechm.schemas import (
    AdverseMediaFinding,
    Claim,
    EvidenceRecord,
    MatchComponentScores,
)

NOW = datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)


def _record(score: float = 0.81, source: str = "OFAC SDN", **components) -> EvidenceRecord:
    defaults = dict(name=0.9, alias=0.8, dob=1.0, nationality=1.0, company=0.5, context=0.6)
    defaults.update(components)
    return EvidenceRecord(
        evidence_id="EVD-001",
        entity_id="CLIENT-2041",
        matched_against="OFAC_SDN_001923",
        match_score=score,
        component_scores=MatchComponentScores(**defaults),
        classification="POSSIBLE_MATCH",
        source=source,
        retrieved_at=NOW,
        metadata={"candidate_name": "Mohammad AL-RASHID"},
    )


class TestScoreScale:
    """Ours is 0-1, theirs is 0-100. Passing 0.81 through unchanged renders a
    confirmed match as near-zero confidence."""

    def test_score_is_rescaled_not_passed_through(self) -> None:
        assert evidence_to_result(_record(score=0.81))["match_confidence"] == 81.0

    def test_scale_constant_matches_their_score_bound(self) -> None:
        assert SCORE_SCALE == 100.0

    def test_confidence_stays_within_their_bounds(self) -> None:
        for score in (0.0, 0.5, 1.0):
            value = evidence_to_result(_record(score=score))["match_confidence"]
            assert 0 <= value <= 100

    def test_float_noise_is_rounded(self) -> None:
        """0.7867 * 100 is 78.67000000000001 in binary float."""
        assert evidence_to_result(_record(score=0.7867))["match_confidence"] == 78.67


class TestDecisionMapping:
    def test_high_corroborated_score_confirms(self) -> None:
        result = evidence_to_result(_record(score=0.9, dob=1.0, nationality=1.0))
        assert result["decision"] == "confirmed_match"

    def test_mid_score_is_likely_match(self) -> None:
        assert evidence_to_result(_record(score=0.7))["decision"] == "likely_match"

    def test_low_score_is_likely_false_positive(self) -> None:
        assert evidence_to_result(_record(score=0.3))["decision"] == "likely_false_positive"

    def test_decisions_are_valid_enum_values(self) -> None:
        valid = {
            "confirmed_match", "likely_match", "needs_review",
            "likely_false_positive", "no_match",
        }
        for score in (0.1, 0.6, 0.9):
            assert evidence_to_result(_record(score=score))["decision"] in valid


class TestNameOnlyMatchIsNeverConfirmed:
    """Their contract: 'A name match ALONE must never yield confirmed_match.'

    name and alias both derive from the same query string, so a record can clear
    0.85 on nothing but a name — the "John Smith the director vs John Smith the
    criminal" case this pipeline exists to prevent.
    """

    def test_name_only_high_score_is_downgraded(self) -> None:
        result = evidence_to_result(
            _record(score=0.885, name=1.0, alias=1.0, dob=0.5,
                    nationality=0.5, company=0.5, context=0.3)
        )
        assert result["decision"] == "needs_review"

    def test_same_score_confirms_once_corroborated(self) -> None:
        """Identical score — only the corroboration differs."""
        result = evidence_to_result(
            _record(score=0.885, name=1.0, alias=1.0, dob=1.0,
                    nationality=1.0, company=0.5, context=0.6)
        )
        assert result["decision"] == "confirmed_match"

    def test_unknown_attributes_do_not_corroborate(self) -> None:
        """0.5 is the 'unknown' value for dob/nationality/company."""
        assert CORROBORATION_FLOOR > 0.5
        result = evidence_to_result(
            _record(score=0.9, name=1.0, alias=1.0, dob=0.5,
                    nationality=0.5, company=0.5, context=0.3)
        )
        assert result["decision"] == "needs_review"

    def test_a_single_corroborating_attribute_is_enough(self) -> None:
        result = evidence_to_result(
            _record(score=0.9, name=1.0, alias=1.0, dob=1.0,
                    nationality=0.5, company=0.5, context=0.3)
        )
        assert result["decision"] == "confirmed_match"


class TestMatchedAttributes:
    def test_lists_only_corroborating_attributes(self) -> None:
        result = evidence_to_result(
            _record(name=0.9, alias=0.8, dob=1.0, nationality=1.0, company=0.5, context=0.3)
        )
        assert result["matched_attributes"] == ["name", "alias", "dob", "nationality"]

    def test_unknown_and_weak_components_are_excluded(self) -> None:
        result = evidence_to_result(_record(company=0.5, context=0.3))
        assert "company" not in result["matched_attributes"]
        assert "context" not in result["matched_attributes"]


class TestSourceProvenance:
    def test_ofac_maps_to_sanctions(self) -> None:
        assert evidence_to_result(_record(source="OFAC SDN"))["source_type"] == "sanctions"

    def test_opensanctions_maps_to_sanctions(self) -> None:
        assert evidence_to_result(_record(source="us_ofac_sdn"))["source_type"] == "sanctions"

    def test_pep_list_maps_to_watchlist(self) -> None:
        result = evidence_to_result(_record(source="PEP position annotations"))
        assert result["source_type"] == "watchlist"

    def test_fixture_marker_survives_downstream(self) -> None:
        """A synthetic record must never pass as an authoritative listing."""
        result = evidence_to_result(_record(source="OFAC SDN (SAMPLE FIXTURE)"))
        assert "SAMPLE FIXTURE" in result["source_name"]


class TestContractShape:
    def test_all_required_fields_present(self) -> None:
        result = evidence_to_result(_record())
        for field in (
            "result_id", "client_id", "source_type", "source_name",
            "match_confidence", "decision", "evaluated_at",
        ):
            assert field in result, f"missing {field}"

    def test_no_risk_field_leaks_through(self) -> None:
        """Their contract deliberately carries no risk field — match_confidence
        is identity resolution, not risk. Part 3 owns risk."""
        assert not any("risk" in key for key in evidence_to_result(_record()))

    def test_evidence_is_traceable(self) -> None:
        result = evidence_to_result(_record())
        assert result["evidence_references"] == ["EVD-001"]
        assert result["result_id"] == "EVD-001"

    def test_timestamp_is_timezone_aware(self) -> None:
        """Their AwareUTC rejects naive datetimes at validation."""
        assert evidence_to_result(_record())["evaluated_at"].tzinfo is not None


class TestAdverseMediaMapping:
    def _finding(self, claims=(), injection=False) -> AdverseMediaFinding:
        return AdverseMediaFinding(
            evidence_id="EVD-310",
            entity_id="CLIENT-2041",
            source_url="https://news.test/article",
            extracted_claims=list(claims),
            injection_attempt_detected=injection,
            retrieved_at=NOW,
        )

    def test_source_type_is_adverse_media(self) -> None:
        assert adverse_media_to_result(self._finding())["source_type"] == "adverse_media"

    def test_never_confirms_identity(self) -> None:
        """An article is not identity corroboration — confirming a customer off
        a namesake in the news is exactly the failure to avoid."""
        claims = [Claim(claim="Under investigation", supported=True, confidence=0.99)]
        assert adverse_media_to_result(self._finding(claims=claims))["decision"] != "confirmed_match"

    def test_no_claims_is_no_match(self) -> None:
        assert adverse_media_to_result(self._finding())["decision"] == "no_match"

    def test_claims_give_likely_match(self) -> None:
        claims = [Claim(claim="Alleged laundering", supported=True, confidence=0.8)]
        assert adverse_media_to_result(self._finding(claims=claims))["decision"] == "likely_match"

    def test_injection_forces_review_despite_confident_claims(self) -> None:
        """Injected content is not trustworthy input to an automated decision."""
        claims = [Claim(claim="Alleged laundering", supported=True, confidence=0.99)]
        result = adverse_media_to_result(self._finding(claims=claims, injection=True))
        assert result["decision"] == "needs_review"

    def test_confidence_is_rescaled(self) -> None:
        claims = [Claim(claim="x", supported=True, confidence=0.8)]
        assert adverse_media_to_result(self._finding(claims=claims))["match_confidence"] == 80.0


class TestValidatesAgainstPart1Schema:
    """The adapter is worthless if Part 1's model rejects its output."""

    def test_evidence_result_validates(self) -> None:
        pytest.importorskip("app.schemas.entity_intelligence")
        from projecttechm.contracts import to_entity_intelligence_result

        result = to_entity_intelligence_result(_record())
        assert result.client_id == "CLIENT-2041"
        assert result.match_confidence == 81.0

    def test_adverse_media_result_validates(self) -> None:
        pytest.importorskip("app.schemas.entity_intelligence")
        from app.schemas.entity_intelligence import EntityIntelligenceResult

        finding = AdverseMediaFinding(
            evidence_id="EVD-310", entity_id="CLIENT-2041",
            source_url="https://news.test/a",
            extracted_claims=[Claim(claim="x", supported=True, confidence=0.8)],
            retrieved_at=NOW,
        )
        assert EntityIntelligenceResult(**adverse_media_to_result(finding)).source_type == "adverse_media"

    def test_extra_fields_are_rejected_downstream(self) -> None:
        """Their CanonicalModel sets extra='forbid', so a stray key is a hard
        failure — not a warning. Proves the adapter emits no extras."""
        pytest.importorskip("app.schemas.entity_intelligence")
        from pydantic import ValidationError

        from app.schemas.entity_intelligence import EntityIntelligenceResult

        payload = evidence_to_result(_record())
        EntityIntelligenceResult(**payload)  # clean payload validates

        with pytest.raises(ValidationError):
            EntityIntelligenceResult(**{**payload, "risk_score": 82})
