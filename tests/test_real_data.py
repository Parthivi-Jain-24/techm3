"""Tests against the real OFAC SDN and OpenSanctions downloads.

Skipped when the files are absent (they are large and gitignored), so a fresh
clone still gets a green suite. Run `python scripts/download_data.py` to enable.

These cover the failure modes that only appear on real data: Treasury publishes
sdn.csv without a header row, uses "-0-" as a null marker, and emits ragged
rows; OpenSanctions ships ~1.32M rows with fields larger than csv's default
field-size limit.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from projecttechm.data_loader import KYC_SCHEMAS, load_ofac_sdn, load_opensanctions
from projecttechm.resolution import CandidateIndex, resolve_against_candidates

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SANCTIONS_DIR = PROJECT_ROOT / "data" / "sanctions"

REAL_SDN = SANCTIONS_DIR / "ofac_sdn.csv"
REAL_ALT = SANCTIONS_DIR / "ofac_alt.csv"
REAL_OPENSANCTIONS = SANCTIONS_DIR / "opensanctions_targets.csv"

requires_ofac = pytest.mark.skipif(
    not REAL_SDN.exists(), reason="real OFAC SDN not downloaded"
)
requires_opensanctions = pytest.mark.skipif(
    not REAL_OPENSANCTIONS.exists(), reason="real OpenSanctions not downloaded"
)


@pytest.fixture(scope="module")
def real_ofac():
    return load_ofac_sdn(REAL_SDN, REAL_ALT if REAL_ALT.exists() else None)


# ---------------------------------------------------------------------------
# OFAC SDN — the headerless real file
# ---------------------------------------------------------------------------

@requires_ofac
class TestRealOfacSdn:
    def test_loads_thousands_not_zero(self, real_ofac) -> None:
        """DictReader without explicit fieldnames silently yielded 0 entities."""
        assert len(real_ofac) > 15_000

    def test_first_row_not_eaten_as_header(self, real_ofac) -> None:
        """A headerless file loses its first entity if a header is assumed."""
        names = {e.name.upper() for e in real_ofac}
        assert "AEROCARIBBEAN AIRLINES" in names

    def test_null_marker_never_leaks_into_fields(self, real_ofac) -> None:
        """'-0-' is OFAC's null marker and must never survive as a field value.

        Checked as whole-field equality, not substring: real remarks legitimately
        contain it inside identifiers (e.g. "US FEIN CH-217-0-431-423-3").
        """
        for entity in real_ofac:
            assert entity.context != "-0-"
            assert entity.dob != "-0-"
            assert entity.nationality != "-0-"
            assert entity.name != "-0-"

    def test_context_is_none_rather_than_null_marker(self, real_ofac) -> None:
        """An entity with no Title and no Remarks gets context=None, not '-0- -0-'."""
        contextless = [e for e in real_ofac if not e.context]
        assert contextless, "expected some entities with neither Title nor Remarks"
        assert all(e.context is None for e in contextless)

    def test_entity_ids_are_unique(self, real_ofac) -> None:
        ids = [e.entity_id for e in real_ofac]
        assert len(ids) == len(set(ids))

    def test_names_are_never_blank(self, real_ofac) -> None:
        assert all(e.name.strip() for e in real_ofac)

    @pytest.mark.skipif(not REAL_ALT.exists(), reason="real OFAC ALT not downloaded")
    def test_aliases_attached_from_alt_file(self, real_ofac) -> None:
        with_aliases = [e for e in real_ofac if e.aliases]
        assert len(with_aliases) > 5_000

    def test_dob_parsed_from_remarks(self, real_ofac) -> None:
        with_dob = [e for e in real_ofac if e.dob]
        assert len(with_dob) > 3_000

    def test_individuals_are_classified(self, real_ofac) -> None:
        individuals = [e for e in real_ofac if e.entity_type == "individual"]
        assert len(individuals) > 3_000

    def test_comma_names_normalised(self, real_ofac) -> None:
        """'LAST, First' must be flipped so prefix blocking works."""
        assert not any(e.name.startswith(",") for e in real_ofac)


# ---------------------------------------------------------------------------
# OpenSanctions — the 1.32M-row real file
# ---------------------------------------------------------------------------

@requires_opensanctions
class TestRealOpenSanctions:
    def test_limit_is_respected(self) -> None:
        assert len(load_opensanctions(REAL_OPENSANCTIONS, limit=1_000)) == 1_000

    def test_oversized_fields_do_not_raise(self) -> None:
        """Real rows exceed csv's 128 KB default field-size limit."""
        assert load_opensanctions(REAL_OPENSANCTIONS, limit=5_000)

    def test_defaults_to_kyc_screenable_schemas(self) -> None:
        entities = load_opensanctions(REAL_OPENSANCTIONS, limit=5_000)
        assert all(e.entity_type in {"individual", "entity"} for e in entities)
        assert entities

    def test_schema_filter_can_be_disabled(self) -> None:
        """Passing schemas=None keeps vessels, securities and crypto wallets."""
        filtered = load_opensanctions(REAL_OPENSANCTIONS, limit=20_000)
        unfiltered = load_opensanctions(REAL_OPENSANCTIONS, limit=20_000, schemas=None)
        assert len(unfiltered) == 20_000
        # The filter drops rows, so the same limit spans further into the file.
        assert {e.entity_id for e in filtered} != {e.entity_id for e in unfiltered}

    def test_person_schema_maps_to_individual(self) -> None:
        entities = load_opensanctions(
            REAL_OPENSANCTIONS, limit=2_000, schemas=frozenset({"Person"})
        )
        assert entities
        assert all(e.entity_type == "individual" for e in entities)

    def test_kyc_schemas_excludes_vessels(self) -> None:
        assert "Vessel" not in KYC_SCHEMAS
        assert "Security" not in KYC_SCHEMAS
        assert "Person" in KYC_SCHEMAS


# ---------------------------------------------------------------------------
# Retrieval at real scale — the reason the full-scan fallback had to go
# ---------------------------------------------------------------------------

@requires_opensanctions
class TestRetrievalAtScale:
    @pytest.fixture(scope="class")
    def big_index(self) -> CandidateIndex:
        return CandidateIndex(load_opensanctions(REAL_OPENSANCTIONS, limit=100_000))

    def test_prefix_miss_does_not_scan_everything(self, big_index: CandidateIndex) -> None:
        """The old fallback returned the whole list, fuzzy-matching 1.3M rows."""
        candidates = big_index.retrieve("Zzzqqxxvv Nonexistent Person")
        assert len(candidates) < 1_000
        assert len(candidates) < big_index.size

    def test_retrieval_is_a_small_fraction_of_the_index(self, big_index: CandidateIndex) -> None:
        candidates = big_index.retrieve("Mohammed Al Rashid")
        assert candidates
        assert len(candidates) < big_index.size * 0.2

    def test_screening_is_bounded_by_limit(self, big_index: CandidateIndex) -> None:
        """A common given name yields far more than 25 weak POSSIBLE_MATCHes."""
        matches = resolve_against_candidates(
            {"entity_id": "X", "name": "Mohammed Al Rashid", "nationality": "AE"},
            big_index,
            limit=25,
        )
        assert len(matches) <= 25

    def test_limit_none_returns_everything(self, big_index: CandidateIndex) -> None:
        query = {"entity_id": "X", "name": "Mohammed Al Rashid", "nationality": "AE"}
        capped = resolve_against_candidates(query, big_index, limit=5)
        uncapped = resolve_against_candidates(query, big_index, limit=None)
        assert len(uncapped) >= len(capped)
        assert len(capped) <= 5

    def test_results_still_sorted_after_capping(self, big_index: CandidateIndex) -> None:
        matches = resolve_against_candidates(
            {"entity_id": "X", "name": "Mohammed Al Rashid"}, big_index, limit=10
        )
        scores = [m.match_score for m in matches]
        assert scores == sorted(scores, reverse=True)


# ---------------------------------------------------------------------------
# Memory footprint — what makes full-coverage screening possible
# ---------------------------------------------------------------------------

class TestEntityFootprint:
    """SanctionedEntity must stay slotted.

    As a pydantic BaseModel it cost ~1,617 bytes/instance, so the full
    OpenSanctions list needed ~2.1 GB of models and could not be loaded. If this
    ever goes back to a BaseModel, full coverage silently stops fitting.
    """

    def test_entity_is_slotted(self) -> None:
        from projecttechm.schemas import SanctionedEntity

        assert hasattr(SanctionedEntity, "__slots__")
        assert not hasattr(SanctionedEntity(entity_id="x", name="y", source_list="z"), "__dict__")

    def test_entity_stays_lean(self) -> None:
        import tracemalloc

        from projecttechm.schemas import SanctionedEntity

        tracemalloc.start()
        items = [
            SanctionedEntity(
                entity_id=f"os-{i}", name=f"Person Number {i}", source_list="opensanctions",
                dob="1975-03-15", nationality="AE", entity_type="individual",
            )
            for i in range(5_000)
        ]
        current, _ = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        per_entity = current / len(items)
        # Real-data average is ~624 B; a BaseModel was ~1,617 B.
        assert per_entity < 900, f"{per_entity:.0f} B/entity — footprint regressed"

    def test_keyword_only_construction(self) -> None:
        """Positional args must not silently bind to the wrong field."""
        from projecttechm.schemas import SanctionedEntity

        with pytest.raises(TypeError):
            SanctionedEntity("os-1", "Some Name", "opensanctions")  # type: ignore[misc]


@requires_opensanctions
class TestFullCoverageIsViable:
    def test_repeated_strings_are_shared(self) -> None:
        """Interning is what keeps 1.28M rows of country codes affordable."""
        entities = load_opensanctions(REAL_OPENSANCTIONS, limit=20_000)
        with_nationality = [e for e in entities if e.nationality]
        assert len(with_nationality) > 100

        # Same value must be the same object, not a per-row copy.
        by_value: dict[str, list[int]] = {}
        for entity in with_nationality:
            by_value.setdefault(entity.nationality, []).append(id(entity.nationality))
        repeated = [ids for ids in by_value.values() if len(ids) > 1]
        assert repeated, "expected some nationality to repeat across rows"
        assert all(len(set(ids)) == 1 for ids in repeated)

    def test_opensanctions_url_is_derivable(self) -> None:
        """The per-entity URL is computed, not stored (~120 MB saved)."""
        from projecttechm.data_loader import opensanctions_url

        entities = load_opensanctions(REAL_OPENSANCTIONS, limit=100)
        assert all(e.source_url is None for e in entities)
        assert opensanctions_url("os-001923") == "https://opensanctions.org/entities/os-001923/"


# ---------------------------------------------------------------------------
# Playbook §9 false positive at full scale
# ---------------------------------------------------------------------------

@requires_opensanctions
class TestNamesakeDisambiguationAtScale:
    """The §9 contract: don't confuse our Rahul Sharma with the sanctioned one.

    The real list contains entities literally named "Rahul Sharma". The test is
    not "return nothing" — at 1.28M entities a shared surname plus a shared
    country can clear the 0.55 POSSIBLE threshold, which is a property of the
    threshold, not a resolution failure. The contract is that the *namesake*
    with a contradicting DOB, country, and company is not matched.
    """

    @pytest.fixture(scope="class")
    def index(self) -> CandidateIndex:
        entities = load_ofac_sdn(REAL_SDN, REAL_ALT if REAL_ALT.exists() else None)
        entities += load_opensanctions(REAL_OPENSANCTIONS, limit=150_000)
        return CandidateIndex(entities)

    def test_namesake_with_contradicting_dob_is_not_confirmed(
        self, index: CandidateIndex
    ) -> None:
        matches = resolve_against_candidates(
            {
                "entity_id": "CUST-8832",
                "name": "Rahul Sharma",
                "dob": "1992",
                "nationality": "UK",
                "company": "Sharma & Partners LLP",
                "context": "Financial advisor based in London",
            },
            index,
        )
        assert not any(m.classification == "CONFIRMED_MATCH" for m in matches)

    def test_contradicting_dob_scores_zero_not_neutral(self) -> None:
        """A known-and-different DOB must not be treated as merely unknown."""
        from projecttechm.scoring import dob_match

        assert dob_match("1992", "1980") == 0.0
        assert dob_match("1992", None) == 0.5
