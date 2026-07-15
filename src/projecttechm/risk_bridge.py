"""Optional bridge that feeds real Part 2 screening into Part 3's risk engine.

Part 3 (`risk_engine`) currently builds its `sanctions` section from a CSV flag:

    "sanctions": {
        "has_match": bool(sanctions_flag),        # a column in the KYC csv
        "match_confidence": 0.92 if flag else ..., # hardcoded
        "source": "Local KYC sanctions flags",     # never screened a name
    }

That is a placeholder — it never screens the customer name against OFAC or
OpenSanctions. This module replaces the placeholder with a real screening
result, resolved through Part 2's CandidateIndex and translated to the shape and
0-1 scale `risk_engine.scoring` expects (via `contracts.to_risk_sanctions_signal`).

It is deliberately a *separate, opt-in* module, not an edit to Part 3's code:

  * Part 3 stays runnable without Part 2 — importing this is a choice their
    owner makes, and the fallback below means a failure here degrades to their
    existing behaviour rather than breaking their service.
  * The dependency points Part 3 -> Part 2, matching the playbook data flow
    (screening feeds risk), and never the reverse.

Usage from Part 3, if they choose it:

    from projecttechm.risk_bridge import enrich_sanctions_section
    payload["sanctions"] = enrich_sanctions_section(client, payload["sanctions"])
"""

from __future__ import annotations

from typing import Any

from .contracts import to_risk_sanctions_signal


def screen_client(client: dict[str, Any]) -> dict[str, Any] | None:
    """Screen one client dict against the real sanctions index.

    `client` is a KYC row (needs at least a name; country/sector sharpen it).
    Returns a risk_engine-shaped sanctions section for the top match, or None if
    nothing cleared the threshold. Returns None (not an exception) on any failure
    so a caller can always fall back to its existing signal.
    """
    try:
        from .services import get_registry  # noqa: PLC0415 - lazy: avoid load at import
    except Exception:  # noqa: BLE001
        return None

    query = _client_to_query(client)
    if not query.get("name"):
        return None

    try:
        matches = get_registry().screen(query, limit=1)
    except Exception:  # noqa: BLE001 - screening must never break risk scoring
        return None
    if not matches:
        return None

    return to_risk_sanctions_signal(matches[0])


def enrich_sanctions_section(
    client: dict[str, Any],
    existing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a sanctions section backed by real screening, or the existing one.

    The contract with Part 3: this never *weakens* their signal. If real
    screening finds a match, that match (with its true confidence and source)
    replaces the placeholder. If it finds nothing, the caller's existing section
    is returned unchanged — screening finding no OFAC hit does not overrule a
    flag their KYC data already carries.
    """
    screened = screen_client(client)
    if screened is None:
        return existing or {"has_match": False}

    # Preserve an evidence id the caller already set, so their audit trail keeps
    # its own reference alongside ours.
    if existing and existing.get("evidence_id"):
        screened.setdefault("kyc_evidence_id", existing["evidence_id"])
    return screened


def _client_to_query(client: dict[str, Any]) -> dict[str, Any]:
    """Map a Part 3 / KYC client row onto a Part 2 screening query.

    Tolerant of both shapes in play across the team: the raw challenge CSV
    (`client_name`, `country`) and the normalized contract (`display_name`).
    """
    name = (
        client.get("client_name")
        or client.get("display_name")
        or client.get("name")
        or ""
    )
    country = client.get("country") or client.get("nationality")
    return {
        "entity_id": client.get("client_id") or client.get("entity_id") or "UNKNOWN",
        "name": name,
        "nationality": country,
        "company": name if client.get("client_type", "").lower() != "individual" else None,
        "context": _context_for(client),
    }


def _context_for(client: dict[str, Any]) -> str | None:
    parts = [client.get("client_type"), client.get("sector"), client.get("country")]
    joined = " ".join(str(p) for p in parts if p)
    return joined or None
