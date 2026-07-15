"""Demo entry point — runs the playbook's two regression test cases."""

from __future__ import annotations

from .evidence import evidence_id_gen
from .schemas import SanctionedEntity
from .resolution import CandidateIndex, resolve_entity, resolve_against_candidates


def main() -> None:
    # Reset evidence ID counter for a clean demo run
    evidence_id_gen.reset()

    # -----------------------------------------------------------------------
    # Sanctions list (mock — matches playbook §9 test data)
    # -----------------------------------------------------------------------
    sanctioned_al_rashid = SanctionedEntity(
        entity_id="OFAC_SDN_001923",
        name="Mohammad Al-Rashid",
        aliases=["M. Rashid"],
        dob="1975",
        nationality="UAE",
        entity_type="individual",
        company="ABC Holdings",
        topics=["sanction"],
        source_list="OFAC SDN",
        source_url="https://www.treasury.gov/ofac/downloads/sdn.csv",
        context="Director with corporate ownership links in UAE region",
    )
    sanctioned_sharma = SanctionedEntity(
        entity_id="OFAC_SDN_005412",
        name="Rahul Sharma",
        aliases=[],
        dob="1980",
        nationality="India",
        entity_type="individual",
        company="XYZ Enterprises",
        topics=["sanction"],
        source_list="OFAC SDN",
        context="Technology consultant based in Mumbai",
    )

    # Build a candidate index
    index = CandidateIndex([sanctioned_al_rashid, sanctioned_sharma])

    # -----------------------------------------------------------------------
    # Test Case 1: TRUE POSITIVE (playbook §9)
    # Mohammed Al Rashid (UAE, Director, ABC Holdings)
    #   vs Mohammad Al-Rashid (UAE, DOB 1975, alias M. Rashid)
    # Expected: ~94% confidence, CONFIRMED_MATCH
    # -----------------------------------------------------------------------
    print("=" * 60)
    print("TEST CASE 1: TRUE POSITIVE")
    print("=" * 60)

    query_true_positive = {
        "entity_id": "CUST-2041",
        "name": "Mohammed Al Rashid",
        "dob": "1975",
        "nationality": "UAE",
        "company": "ABC Holdings",
        "context": "Director at ABC Holdings",
        "evidence_id": "EVD-203",
    }
    result = resolve_entity(query_true_positive, sanctioned_al_rashid)
    print(result.model_dump_json(indent=2))

    # -----------------------------------------------------------------------
    # Test Case 2: FALSE POSITIVE (playbook §9)
    # Rahul Sharma (different country/company/DOB/role)
    #   vs sanctioned Rahul Sharma
    # Expected: ~31% confidence, LIKELY_FALSE_POSITIVE
    # -----------------------------------------------------------------------
    print()
    print("=" * 60)
    print("TEST CASE 2: FALSE POSITIVE")
    print("=" * 60)

    query_false_positive = {
        "entity_id": "CUST-8832",
        "name": "Rahul Sharma",
        "dob": "1992",
        "nationality": "UK",
        "company": "Sharma & Partners LLP",
        "context": "Financial advisor based in London",
    }
    result_fp = resolve_entity(query_false_positive, sanctioned_sharma)
    print(result_fp.model_dump_json(indent=2))

    # -----------------------------------------------------------------------
    # Test Case 3: BATCH RESOLUTION via CandidateIndex
    # -----------------------------------------------------------------------
    print()
    print("=" * 60)
    print(f"BATCH RESOLUTION (index size: {index.size} entities)")
    print("=" * 60)

    matches = resolve_against_candidates(query_true_positive, index)
    print(f"Found {len(matches)} match(es) for '{query_true_positive['name']}':")
    for m in matches:
        print(f"  -> {m.matched_against}: {m.match_score:.4f} ({m.classification})")


if __name__ == "__main__":
    main()