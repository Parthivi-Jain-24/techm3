"""Tests for data_loader module against sample datasets."""

from __future__ import annotations

from pathlib import Path

import pytest

from projecttechm.data_loader import (
    load_articles,
    load_clients,
    load_gdpr_articles,
    load_ofac_sdn,
    load_opensanctions,
    load_transactions,
    load_ubo_structure,
)

# Resolve project root from this test file's location
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"


# ---------------------------------------------------------------------------
# OFAC SDN tests
# ---------------------------------------------------------------------------

class TestLoadOfacSdn:
    def test_loads_sample_sdn(self) -> None:
        entities = load_ofac_sdn(
            DATA_DIR / "sanctions" / "sample_ofac_sdn.csv",
            DATA_DIR / "sanctions" / "sample_ofac_alt.csv",
        )
        assert len(entities) > 0

    def test_al_rashid_present(self) -> None:
        entities = load_ofac_sdn(
            DATA_DIR / "sanctions" / "sample_ofac_sdn.csv",
            DATA_DIR / "sanctions" / "sample_ofac_alt.csv",
        )
        names = [e.name for e in entities]
        assert any("Al-Rashid" in n or "AL-RASHID" in n for n in names)

    def test_aliases_loaded_from_alt(self) -> None:
        entities = load_ofac_sdn(
            DATA_DIR / "sanctions" / "sample_ofac_sdn.csv",
            DATA_DIR / "sanctions" / "sample_ofac_alt.csv",
        )
        al_rashid = [e for e in entities if "001923" in e.entity_id][0]
        # Should have aliases from both Remarks and ALT file
        assert len(al_rashid.aliases) >= 2

    def test_dob_parsed_from_remarks(self) -> None:
        entities = load_ofac_sdn(
            DATA_DIR / "sanctions" / "sample_ofac_sdn.csv",
        )
        al_rashid = [e for e in entities if "001923" in e.entity_id][0]
        assert al_rashid.dob is not None
        assert "1975" in al_rashid.dob

    def test_nationality_parsed_from_remarks(self) -> None:
        entities = load_ofac_sdn(
            DATA_DIR / "sanctions" / "sample_ofac_sdn.csv",
        )
        al_rashid = [e for e in entities if "001923" in e.entity_id][0]
        assert al_rashid.nationality is not None
        assert "UAE" in al_rashid.nationality

    def test_entity_type_set(self) -> None:
        entities = load_ofac_sdn(
            DATA_DIR / "sanctions" / "sample_ofac_sdn.csv",
        )
        individuals = [e for e in entities if e.entity_type == "individual"]
        companies = [e for e in entities if e.entity_type == "entity"]
        assert len(individuals) > 0
        assert len(companies) > 0

    def test_missing_file_raises(self) -> None:
        with pytest.raises(FileNotFoundError):
            load_ofac_sdn("nonexistent.csv")


# ---------------------------------------------------------------------------
# OpenSanctions tests
# ---------------------------------------------------------------------------

class TestLoadOpenSanctions:
    def test_loads_sample(self) -> None:
        entities = load_opensanctions(
            DATA_DIR / "sanctions" / "sample_opensanctions.csv"
        )
        assert len(entities) > 0

    def test_aliases_split_by_semicolon(self) -> None:
        entities = load_opensanctions(
            DATA_DIR / "sanctions" / "sample_opensanctions.csv"
        )
        al_rashid = [e for e in entities if "001923" in e.entity_id][0]
        assert len(al_rashid.aliases) >= 2

    def test_individual_vs_entity_type(self) -> None:
        entities = load_opensanctions(
            DATA_DIR / "sanctions" / "sample_opensanctions.csv"
        )
        individuals = [e for e in entities if e.entity_type == "individual"]
        companies = [e for e in entities if e.entity_type == "entity"]
        assert len(individuals) > 0
        assert len(companies) > 0


# ---------------------------------------------------------------------------
# Client data tests
# ---------------------------------------------------------------------------

class TestLoadClients:
    def test_loads_clients(self) -> None:
        clients = load_clients(DATA_DIR / "clients_with_fatf_ofac.csv")
        assert len(clients) == 2000

    def test_client_has_required_fields(self) -> None:
        clients = load_clients(DATA_DIR / "clients_with_fatf_ofac.csv")
        first = clients[0]
        assert "entity_id" in first
        assert "name" in first
        assert "country" in first
        assert "context" in first

    def test_sanctions_flagged_clients_exist(self) -> None:
        clients = load_clients(DATA_DIR / "clients_with_fatf_ofac.csv")
        sanctioned = [c for c in clients if c["sanctions_flag"] == 1]
        assert len(sanctioned) > 0


# ---------------------------------------------------------------------------
# Transactions tests
# ---------------------------------------------------------------------------

class TestLoadTransactions:
    def test_loads_transactions(self) -> None:
        txns = load_transactions(DATA_DIR / "transactions_with_fatf_ofac.csv")
        assert len(txns) == 50000

    def test_transaction_has_required_fields(self) -> None:
        txns = load_transactions(DATA_DIR / "transactions_with_fatf_ofac.csv")
        first = txns[0]
        assert "transaction_id" in first
        assert "client_id" in first
        assert "amount" in first
        assert isinstance(first["amount"], float)


# ---------------------------------------------------------------------------
# UBO structure tests
# ---------------------------------------------------------------------------

class TestLoadUboStructure:
    def test_loads_showcase(self) -> None:
        entities, edges = load_ubo_structure(
            DATA_DIR / "ubo" / "showcase_structure.json"
        )
        assert len(entities) == 4
        assert len(edges) == 3

    def test_loads_simple(self) -> None:
        entities, edges = load_ubo_structure(
            DATA_DIR / "ubo" / "simple_structure.json"
        )
        assert len(entities) == 3
        assert len(edges) == 2

    def test_showcase_has_sanctioned_individual(self) -> None:
        entities, _ = load_ubo_structure(
            DATA_DIR / "ubo" / "showcase_structure.json"
        )
        names = [e.name for e in entities]
        assert any("Al-Rashid" in n for n in names)


# ---------------------------------------------------------------------------
# Articles tests
# ---------------------------------------------------------------------------

class TestLoadArticles:
    def test_loads_articles(self) -> None:
        articles = load_articles(DATA_DIR / "articles")
        assert len(articles) >= 3

    def test_adversarial_article_has_injection(self) -> None:
        articles = load_articles(DATA_DIR / "articles")
        adversarial = [a for a in articles if "adversarial" in a["filename"]]
        assert len(adversarial) == 1
        content = adversarial[0]["content"].lower()
        assert "ignore" in content

    def test_clean_article_no_injection(self) -> None:
        articles = load_articles(DATA_DIR / "articles")
        clean = [a for a in articles if "clean" in a["filename"]]
        assert len(clean) == 1
        content = clean[0]["content"].lower()
        assert "ignore all prior instructions" not in content


# ---------------------------------------------------------------------------
# GDPR tests
# ---------------------------------------------------------------------------

class TestLoadGdpr:
    def test_loads_gdpr_articles(self) -> None:
        articles = load_gdpr_articles(DATA_DIR / "gdpr_articles.csv")
        assert len(articles) > 0

    def test_first_article_is_article1(self) -> None:
        articles = load_gdpr_articles(DATA_DIR / "gdpr_articles.csv")
        assert articles[0]["article_id"] == "article1"


# ---------------------------------------------------------------------------
# OpenSanctions context provenance
# ---------------------------------------------------------------------------

class TestOpenSanctionsContext:
    """`sanctions` is list-membership metadata, not a description.

    Scoring "OFAC SDN - SDGT" as context against a role summary returned 0.085,
    penalising a true match for having no description rather than staying at the
    0.3 "unknown context" neutral.
    """

    def test_context_is_none_not_a_program_code(self) -> None:
        entities = load_opensanctions(DATA_DIR / "sanctions" / "sample_opensanctions.csv")
        assert entities
        assert all(e.context is None for e in entities)

    def test_sanctions_metadata_lands_in_topics(self) -> None:
        entities = load_opensanctions(DATA_DIR / "sanctions" / "sample_opensanctions.csv")
        with_topics = [e for e in entities if e.topics]
        assert with_topics, "sanctions programs must still be retained"
        assert any("SDGT" in t for e in with_topics for t in e.topics)

    def test_unknown_context_scores_neutral_not_penalised(self) -> None:
        """A candidate with no description must not contradict the query."""
        from projecttechm.scoring import contextual_similarity

        assert contextual_similarity("Director at ABC Holdings", None) == 0.3
