"""Tests for the Part 2 -> Part 3 (risk_engine) signal adapter.

Separate from test_contract_adapter.py because these pin a different consumer.
Part 1's EntityIntelligenceResult and Part 3's risk_engine want different shapes
on different scales, and the gap between them is where a silent, catastrophic
bug lives:

    Part 1 contract : match_confidence is Score = 0-100
    Part 3 consumer : clamp(confidence, 0.0, 1.0)

Passing the contract straight into the engine clamps every value >= 1.0 to 1.0,
so a 0.31 likely-false-positive and a 0.94 confirmed match both score full
points. Risk tops out on every hit and the number still looks plausible.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from projecttechm.contracts import (
    TRUSTED_SOURCES,
    UBO_RELATIONSHIPS,
    evidence_to_result,
    to_risk_media_signal,
    to_risk_sanctions_signal,
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


def _finding(claims=(), injection: bool = False) -> AdverseMediaFinding:
    return AdverseMediaFinding(
        evidence_id="EVD-310",
        entity_id="CLIENT-2041",
        source_url="https://news.test/a",
        extracted_claims=list(claims),
        injection_attempt_detected=injection,
        retrieved_at=NOW,
    )


class TestScaleConflict:
    def test_risk_signal_confidence_is_zero_to_one(self) -> None:
        signal = to_risk_sanctions_signal(_record(score=0.81))
        assert signal["match_confidence"] == 0.81
        assert 0.0 <= signal["match_confidence"] <= 1.0

    def test_the_two_consumers_disagree_by_design(self) -> None:
        record = _record(score=0.81)
        assert evidence_to_result(record)["match_confidence"] == 81.0
        assert to_risk_sanctions_signal(record)["match_confidence"] == 0.81

    def test_risk_engine_can_tell_strong_from_weak(self) -> None:
        """The regression this adapter exists to prevent."""
        pytest.importorskip("risk_engine")
        from risk_engine.scoring import make_factor

        strong = to_risk_sanctions_signal(_record(score=0.94))["match_confidence"]
        weak = to_risk_sanctions_signal(_record(score=0.31))["match_confidence"]
        assert (
            make_factor("x", 18, strong, "r").contribution
            > make_factor("x", 18, weak, "r").contribution
        )

    def test_raw_contract_value_would_collapse(self) -> None:
        """Documents the bug: 0-100 into risk_engine gives full points either way."""
        pytest.importorskip("risk_engine")
        from risk_engine.scoring import make_factor

        assert make_factor("x", 18, 94.0, "r").contribution == 18.0
        assert make_factor("x", 18, 31.0, "r").contribution == 18.0


class TestSanctionsSignal:
    def test_has_match_for_a_real_match(self) -> None:
        assert to_risk_sanctions_signal(_record())["has_match"] is True

    def test_no_match_for_a_false_positive(self) -> None:
        record = _record()
        record.classification = "LIKELY_FALSE_POSITIVE"
        assert to_risk_sanctions_signal(record)["has_match"] is False

    def test_source_normalised_to_what_risk_engine_tests_for(self) -> None:
        """risk_engine awards its trusted-source bonus on exact strings only."""
        assert to_risk_sanctions_signal(_record(source="OFAC SDN"))["source"] in TRUSTED_SOURCES
        assert to_risk_sanctions_signal(_record(source="us_ofac_sdn"))["source"] in TRUSTED_SOURCES

    def test_fixture_never_earns_the_trusted_source_bonus(self) -> None:
        """A synthetic record must not inflate a real risk score."""
        signal = to_risk_sanctions_signal(_record(source="OFAC SDN (SAMPLE FIXTURE)"))
        assert signal["source"] not in TRUSTED_SOURCES

    def test_relationship_marks_an_ownership_chain_hit(self) -> None:
        signal = to_risk_sanctions_signal(_record(), relationship="Director")
        assert signal["relationship"] == "director"
        assert signal["relationship"] in UBO_RELATIONSHIPS

    def test_direct_hit_carries_no_relationship(self) -> None:
        assert "relationship" not in to_risk_sanctions_signal(_record())

    def test_evidence_id_is_carried(self) -> None:
        assert to_risk_sanctions_signal(_record())["evidence_id"] == "EVD-001"


class TestMediaSignal:
    def test_claims_produce_negative_news(self) -> None:
        claims = [Claim(claim="Alleged laundering", supported=True, confidence=0.8)]
        signal = to_risk_media_signal(_finding(claims=claims))
        assert signal["negative_news_found"] is True
        assert signal["confidence"] == 0.8  # 0-1, not 80

    def test_injected_article_cannot_move_the_risk_score(self) -> None:
        """Otherwise an attacker who plants an article gains a lever on risk —
        the inverse of the attack the guard blocks, and just as damaging."""
        claims = [Claim(claim="Alleged laundering", supported=True, confidence=0.99)]
        assert to_risk_media_signal(_finding(claims=claims, injection=True))[
            "negative_news_found"
        ] is False

    def test_no_claims_means_no_negative_news(self) -> None:
        assert to_risk_media_signal(_finding())["negative_news_found"] is False


class TestEndToEndIntoRiskEngine:
    """Part 2 output into Part 3's engine, for real."""

    def test_engine_accepts_our_signal(self) -> None:
        pytest.importorskip("risk_engine")
        from risk_engine import RiskEngine

        assessment = RiskEngine().assess(
            {"customer_id": "CLIENT-2041", "sanctions": to_risk_sanctions_signal(_record(0.94))}
        ).to_dict()
        assert assessment["risk_score"] > 0
        assert assessment["risk_level"] in {"LOW", "MEDIUM", "HIGH", "CRITICAL"}

    def test_stronger_match_yields_higher_risk(self) -> None:
        pytest.importorskip("risk_engine")
        from risk_engine import RiskEngine

        engine = RiskEngine()
        strong = engine.assess(
            {"customer_id": "C1", "sanctions": to_risk_sanctions_signal(_record(0.94))}
        ).to_dict()["risk_score"]
        weak = engine.assess(
            {"customer_id": "C2", "sanctions": to_risk_sanctions_signal(_record(0.60))}
        ).to_dict()["risk_score"]
        assert strong > weak

    def test_our_evidence_id_survives_the_hop(self) -> None:
        """Part 4's SAR can only cite evidence that reaches the assessment."""
        pytest.importorskip("risk_engine")
        from risk_engine import RiskEngine

        assessment = RiskEngine().assess(
            {"customer_id": "CLIENT-2041", "sanctions": to_risk_sanctions_signal(_record(0.94))}
        ).to_dict()
        assert "EVD-001" in assessment["evidence_ids"]
