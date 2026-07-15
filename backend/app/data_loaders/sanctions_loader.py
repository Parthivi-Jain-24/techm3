"""Sanctions screening loader — OFAC SDN + OpenSanctions.

Source files:
    data/sanctions/ofac_sdn.csv  (no header; ~19 K rows)
        Positional columns: ent_num, SDN_Name, SDN_Type, Program,
            Title, Call_Sign, Vess_type, Tonnage, GRT,
            Vess_flag, Vess_owner, Remarks
    data/sanctions/opensanctions_targets.csv  (has header; ~1.3 M rows)
        Key columns used: id, schema, name, aliases, countries, sanctions

Matching strategy
-----------------
Simple case-insensitive substring + token-overlap scoring.  This is NOT
production-grade fuzzy matching — it is intentionally lightweight so the
module loads fast and the LLM agent can reason over the candidates.

Only the *name* and *aliases* fields are searched.  Each candidate is
scored 0-100:
    100  exact match (lowered)
    80   query is a complete substring of name
    60+  token-overlap ratio  (|shared| / |query_tokens|) × 60

Results with score < 40 are dropped.  Caller gets the top *limit* hits.

Memory note: OpenSanctions is large.  We extract only (name, aliases,
country, sanctions_info) into a list of tuples to keep the footprint
manageable (~250 MB for the name index).
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

from app.config import settings

# ── Types ───────────────────────────────────────────────────────────

_SanctionEntry = tuple[str, str, str, str, str]
# (source, name, aliases, country, extra_info)

# ── In-memory cache ─────────────────────────────────────────────────

_entries: list[_SanctionEntry] | None = None

_OFAC_COLUMNS = [
    "ent_num", "SDN_Name", "SDN_Type", "Program", "Title",
    "Call_Sign", "Vess_type", "Tonnage", "GRT",
    "Vess_flag", "Vess_owner", "Remarks",
]

_SENTINEL = "-0-"


def _clean(val: str) -> str:
    v = val.strip().strip('"').strip()
    return "" if v == _SENTINEL else v


def _load_ofac(path: Path) -> list[_SanctionEntry]:
    results: list[_SanctionEntry] = []
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.reader(fh)
        for cols in reader:
            if len(cols) < 4:
                continue
            name = _clean(cols[1])
            if not name:
                continue
            country = _clean(cols[3]) if len(cols) > 3 else ""
            remarks = _clean(cols[11]) if len(cols) > 11 else ""
            aliases = ""
            if remarks.lower().startswith("a.k.a."):
                aliases = remarks
            results.append(("OFAC_SDN", name, aliases, country, remarks))
    return results


def _load_opensanctions(path: Path) -> list[_SanctionEntry]:
    results: list[_SanctionEntry] = []
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            name = (row.get("name") or "").strip()
            if not name:
                continue
            aliases = (row.get("aliases") or "").strip()
            country = (row.get("countries") or "").strip()
            sanctions = (row.get("sanctions") or "").strip()
            results.append(("OpenSanctions", name, aliases, country, sanctions))
    return results


def _load() -> list[_SanctionEntry]:
    global _entries
    if _entries is not None:
        return _entries

    _entries = []

    ofac_path = settings.data_folder / "sanctions" / "ofac_sdn.csv"
    if ofac_path.exists():
        _entries.extend(_load_ofac(ofac_path))

    osanc_path = settings.data_folder / "sanctions" / "opensanctions_targets.csv"
    if osanc_path.exists():
        _entries.extend(_load_opensanctions(osanc_path))

    return _entries


# ── Scoring ─────────────────────────────────────────────────────────

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> set[str]:
    return set(_TOKEN_RE.findall(text.lower()))


def _score(query_lower: str, query_tokens: set[str], name_lower: str, aliases_lower: str) -> int:
    if query_lower == name_lower:
        return 100
    if query_lower in name_lower or query_lower in aliases_lower:
        return 80

    candidate_tokens = _tokenize(name_lower) | _tokenize(aliases_lower)
    if not query_tokens:
        return 0
    overlap = len(query_tokens & candidate_tokens)
    return int((overlap / len(query_tokens)) * 60)


# ── Public API ──────────────────────────────────────────────────────

def get_sanctions_matches(
    name: str,
    *,
    threshold: int = 40,
    limit: int = 10,
) -> list[dict]:
    """Search OFAC SDN + OpenSanctions for *name*.

    Returns up to *limit* dicts sorted by descending score::

        {"source", "name", "aliases", "country", "info", "score"}

    Only entries scoring ≥ *threshold* (0–100) are returned.
    """
    entries = _load()
    q = name.strip().lower()
    if not q:
        return []

    q_tokens = _tokenize(q)
    hits: list[tuple[int, _SanctionEntry]] = []

    for entry in entries:
        src, ename, aliases, country, info = entry
        s = _score(q, q_tokens, ename.lower(), aliases.lower())
        if s >= threshold:
            hits.append((s, entry))

    hits.sort(key=lambda h: h[0], reverse=True)
    return [
        {
            "source": e[0],
            "name": e[1],
            "aliases": e[2],
            "country": e[3],
            "info": e[4],
            "score": sc,
        }
        for sc, e in hits[:limit]
    ]
