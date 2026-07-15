"""Tests for the opt-in Part 2 -> Part 3 screening bridge.

The bridge replaces risk_engine's placeholder sanctions signal (a CSV flag,
source "Local KYC sanctions flags", hardcoded confidence) with a real screening
result. Its contract with Part 3 is the load-bearing part: it must never weaken
their signal, and it must never break their service.
"""

from __future__ import annotations

import pytest

from projecttechm.risk_bridge import (
    _client_to_query,
    enrich_sanctions_section,
    screen_client,
)


@pytest.fixture(autouse=True)
def _fixtures_mode(monkeypatch):
    """Screen against the deterministic sample fixtures, not the real lists."""
    monkeypatch.setenv("PROJECTTECHM_SANCTIONS_MODE", "sample")
    from projecttechm.services import reset_registry

    reset_registry()
    yield
    reset_registry()


class TestClientToQuery:
    def test_reads_challenge_csv_shape(self) -> None:
        query = _client_to_query(
            {"client_id": "CLIENT-1", "client_name": "Acme Ltd", "country": "AE"}
        )
        assert query["name"] == "Acme Ltd"
        assert query["nationality"] == "AE"
        assert query["entity_id"] == "CLIENT-1"

    def test_reads_normalized_contract_shape(self) -> None:
        query = _client_to_query(
            {"client_id": "CLIENT-1", "display_name": "Acme Ltd", "country": "AE"}
        )
        assert query["name"] == "Acme Ltd"

    def test_individual_carries_no_company(self) -> None:
        query = _client_to_query(
            {"client_id": "C1", "client_name": "Jane Doe", "client_type": "Individual"}
        )
        assert query["company"] is None

    def test_corporate_uses_name_as_company(self) -> None:
        query = _client_to_query(
            {"client_id": "C1", "client_name": "Acme Ltd", "client_type": "Corporate"}
        )
        assert query["company"] == "Acme Ltd"


class TestScreenClient:
    def test_matching_name_produces_a_signal(self) -> None:
        signal = screen_client(
            {"client_id": "CLIENT-2041", "client_name": "Mohammed Al Rashid",
             "client_type": "Corporate", "country": "UAE"}
        )
        assert signal is not None
        assert signal["has_match"] is True
        assert 0.0 <= signal["match_confidence"] <= 1.0  # 0-1, risk_engine's scale

    def test_clean_name_returns_none(self) -> None:
        assert screen_client(
            {"client_id": "C-99", "client_name": "Greenfield Technologies Pte Ltd",
             "client_type": "Corporate", "country": "SG"}
        ) is None

    def test_missing_name_returns_none(self) -> None:
        assert screen_client({"client_id": "C-1"}) is None


class TestEnrichNeverWeakensTheSignal:
    """The contract with Part 3: enrichment replaces on a hit, preserves on a miss."""

    def test_real_match_replaces_the_placeholder(self) -> None:
        placeholder = {"has_match": False, "source": "Local KYC sanctions flags"}
        enriched = enrich_sanctions_section(
            {"client_id": "CLIENT-2041", "client_name": "Mohammed Al Rashid",
             "client_type": "Corporate", "country": "UAE"},
            placeholder,
        )
        assert enriched["has_match"] is True
        assert enriched["source"] != "Local KYC sanctions flags"

    def test_no_match_preserves_the_existing_flag(self) -> None:
        """Screening finding no OFAC hit must not overrule a KYC flag they set."""
        existing = {"has_match": True, "source": "Local KYC sanctions flags",
                    "match_confidence": 0.92}
        enriched = enrich_sanctions_section(
            {"client_id": "C-99", "client_name": "Greenfield Technologies Pte Ltd",
             "client_type": "Corporate", "country": "SG"},
            existing,
        )
        assert enriched == existing

    def test_no_existing_and_no_match_gives_safe_default(self) -> None:
        enriched = enrich_sanctions_section(
            {"client_id": "C-99", "client_name": "Greenfield Technologies Pte Ltd"},
            None,
        )
        assert enriched == {"has_match": False}

    def test_caller_evidence_id_is_preserved_alongside_ours(self) -> None:
        enriched = enrich_sanctions_section(
            {"client_id": "CLIENT-2041", "client_name": "Mohammed Al Rashid",
             "client_type": "Corporate", "country": "UAE"},
            {"has_match": False, "evidence_id": "SAN-CLIENT-2041"},
        )
        assert enriched["kyc_evidence_id"] == "SAN-CLIENT-2041"
        assert enriched["evidence_id"] != "SAN-CLIENT-2041"  # ours, the real match


class TestEndToEndThroughRiskEngine:
    def test_matched_client_scores_higher_than_clean(self) -> None:
        pytest.importorskip("risk_engine")
        from risk_engine import RiskEngine

        engine = RiskEngine()
        matched = engine.assess({
            "customer_id": "CLIENT-2041",
            "sanctions": enrich_sanctions_section(
                {"client_id": "CLIENT-2041", "client_name": "Mohammed Al Rashid",
                 "client_type": "Corporate", "country": "UAE"},
                {"has_match": False},
            ),
        }).to_dict()

        clean = engine.assess({
            "customer_id": "C-99",
            "sanctions": enrich_sanctions_section(
                {"client_id": "C-99", "client_name": "Greenfield Technologies Pte Ltd",
                 "client_type": "Corporate", "country": "SG"},
                {"has_match": False},
            ),
        }).to_dict()

        assert matched["risk_score"] > clean["risk_score"]

    def test_screened_evidence_reaches_the_assessment(self) -> None:
        pytest.importorskip("risk_engine")
        from risk_engine import RiskEngine

        signal = enrich_sanctions_section(
            {"client_id": "CLIENT-2041", "client_name": "Mohammed Al Rashid",
             "client_type": "Corporate", "country": "UAE"},
            {"has_match": False},
        )
        assessment = RiskEngine().assess(
            {"customer_id": "CLIENT-2041", "sanctions": signal}
        ).to_dict()
        assert signal["evidence_id"] in assessment["evidence_ids"]


class TestFailsSafe:
    def test_registry_failure_returns_none_not_raises(self, monkeypatch) -> None:
        """If the registry itself throws mid-screen, screen_client swallows it."""
        from projecttechm import services

        def _boom():
            raise RuntimeError("registry exploded")

        monkeypatch.setattr(services, "get_registry", _boom)
        assert screen_client({"client_id": "C1", "client_name": "X"}) is None

    def test_screen_failure_preserves_existing_signal(self, monkeypatch) -> None:
        """A failure in Part 2 must degrade to Part 3's signal, not break it."""
        from projecttechm import services

        monkeypatch.setattr(
            services, "get_registry",
            lambda: (_ for _ in ()).throw(RuntimeError("down")),
        )
        existing = {"has_match": True, "source": "Local KYC sanctions flags"}
        assert enrich_sanctions_section({"client_id": "C1", "client_name": "X"}, existing) == existing
