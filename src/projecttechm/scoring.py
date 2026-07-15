"""Scoring helpers: fuzzy matching, semantic context, weights, and classification."""

from __future__ import annotations

import re
from functools import lru_cache

from rapidfuzz import fuzz

from .schemas import MatchComponentScores

CONFIRMED_THRESHOLD = 0.85
POSSIBLE_THRESHOLD = 0.55

# ---------------------------------------------------------------------------
# Optional semantic embedding support
# Falls back gracefully to fuzzy matching if sentence-transformers is absent.
# ---------------------------------------------------------------------------
SEMANTIC_MODEL_NAME = "all-MiniLM-L6-v2"

_semantic_model = None
_semantic_available = False

try:
    from sentence_transformers import SentenceTransformer, util as st_util

    try:
        # Load from the local cache first. SentenceTransformer otherwise calls the
        # HuggingFace Hub on *every* import to check for a newer revision, which
        # blocks for minutes on a slow or captive network and makes both server
        # startup and the test suite nondeterministic (observed: 6.5s cached vs
        # multi-minute hangs online). Falls through to a download on first run.
        _semantic_model = SentenceTransformer(SEMANTIC_MODEL_NAME, local_files_only=True)
    except Exception:  # noqa: BLE001 - not cached yet, or cache unreadable
        _semantic_model = SentenceTransformer(SEMANTIC_MODEL_NAME)
    _semantic_available = True
except ImportError:
    pass


def is_semantic_available() -> bool:
    """Return whether sentence-transformers is installed and the model loaded."""
    return _semantic_available


def warm_semantic_model() -> bool:
    """Run one throwaway encode so the first real query does not pay for it.

    Torch defers a lot of setup to the first forward pass — several seconds of
    it. Without warming, that lands on whoever calls /screen first. Returns
    whether a warm-up actually ran.
    """
    if not _semantic_available or _semantic_model is None:
        return False
    contextual_similarity("warmup", "warmup")
    return True


# ---------------------------------------------------------------------------
# Fuzzy string matching
# ---------------------------------------------------------------------------

def normalized_similarity(left: str | None, right: str | None) -> float:
    """Best of whole-string and token-order-insensitive similarity.

    Deliberately excludes `partial_ratio` and `token_set_ratio`. Both are
    substring/subset matchers and are catastrophic for entity screening: they
    score a short sanctioned name as a perfect hit inside any longer unrelated
    name ("Aegean Ventures Cyprus Ltd" vs "VENTURE" -> partial_ratio 100), which
    floods reviewers with false positives at real list scale.

    `ratio` catches spelling variants (Mohammed/Mohammad -> 89) and
    `token_sort_ratio` catches reordering ("Rashid, Mohammed"), which together
    cover the playbook's §9 cases without the false-positive blowup.
    """
    if not left or not right:
        return 0.0
    left_normalized = left.lower()
    right_normalized = right.lower()
    return max(
        fuzz.ratio(left_normalized, right_normalized),
        fuzz.token_sort_ratio(left_normalized, right_normalized),
    ) / 100.0


def alias_similarity(query_name: str, aliases: list[str] | None) -> float:
    if not aliases:
        return 0.0
    return max((normalized_similarity(query_name, alias) for alias in aliases), default=0.0)


def exact_or_unknown_match(left: str | None, right: str | None) -> float:
    if not left or not right:
        return 0.5
    return 1.0 if left.strip().lower() == right.strip().lower() else 0.0


def fuzzy_or_unknown_match(left: str | None, right: str | None) -> float:
    """Fuzzy similarity that stays neutral on missing data.

    `normalized_similarity` returns 0.0 for a missing side, which *penalises* an
    unknown as if it were a contradiction. Sanctions lists routinely omit
    company, so this returns 0.5 instead — "unknown, don't penalize or reward".
    """
    if not left or not right:
        return 0.5
    return normalized_similarity(left, right)


# ---------------------------------------------------------------------------
# Country comparison
# ---------------------------------------------------------------------------

# The loaders emit different shapes for the same country: OFAC remarks give
# names ("nationality Russia"), OpenSanctions gives ISO alpha-2 ("RU"). Without
# normalisation the same nationality scores as a contradiction across sources.
_COUNTRY_ALIASES = {
    "ae": "AE", "uae": "AE", "united arab emirates": "AE",
    "af": "AF", "afghanistan": "AF",
    "au": "AU", "australia": "AU",
    "ca": "CA", "canada": "CA",
    "ch": "CH", "switzerland": "CH",
    "cn": "CN", "china": "CN", "people's republic of china": "CN", "prc": "CN",
    "cy": "CY", "cyprus": "CY",
    "de": "DE", "germany": "DE",
    "fr": "FR", "france": "FR",
    "gb": "GB", "uk": "GB", "united kingdom": "GB", "great britain": "GB", "england": "GB",
    "hk": "HK", "hong kong": "HK",
    "in": "IN", "india": "IN",
    "ir": "IR", "iran": "IR", "islamic republic of iran": "IR",
    "jp": "JP", "japan": "JP",
    "kp": "KP", "north korea": "KP", "dprk": "KP", "korea, north": "KP",
    "kr": "KR", "south korea": "KR", "korea, south": "KR",
    "ky": "KY", "cayman islands": "KY",
    "lb": "LB", "lebanon": "LB",
    "nl": "NL", "netherlands": "NL",
    "pa": "PA", "panama": "PA",
    "qa": "QA", "qatar": "QA",
    "ru": "RU", "russia": "RU", "russian federation": "RU",
    "sd": "SD", "sudan": "SD",
    "sg": "SG", "singapore": "SG",
    "sy": "SY", "syria": "SY", "syrian arab republic": "SY",
    "us": "US", "usa": "US", "united states": "US", "united states of america": "US",
    "ve": "VE", "venezuela": "VE",
    "vg": "VG", "british virgin islands": "VG",
    "vn": "VN", "vietnam": "VN", "viet nam": "VN",
}


def normalize_country(value: str | None) -> str | None:
    """Fold a country name or code to ISO alpha-2 where known."""
    if not value:
        return None
    key = value.strip().lower()
    if key in _COUNTRY_ALIASES:
        return _COUNTRY_ALIASES[key]
    return value.strip().upper()


def country_match(left: str | None, right: str | None) -> float:
    """Compare countries after normalising codes and names to a common form."""
    if not left or not right:
        return 0.5
    return 1.0 if normalize_country(left) == normalize_country(right) else 0.0


# ---------------------------------------------------------------------------
# DOB comparison
# ---------------------------------------------------------------------------

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def parse_dob(value: str | None) -> tuple[int | None, int | None, int | None] | None:
    """Parse a date of birth into (year, month, day); unknown parts are None.

    Handles the formats the loaders actually emit: OFAC remarks give
    "15 Mar 1975" or "1975", OpenSanctions gives "1975-03-15" or "1975".
    Returns None if no year can be found.
    """
    if not value:
        return None
    text = value.strip().lower()

    # ISO-ish: 1975-03-15 / 1975-03 / 1975/03/15
    iso = re.match(r"^(\d{4})(?:[-/](\d{1,2}))?(?:[-/](\d{1,2}))?$", text)
    if iso:
        year, month, day = iso.groups()
        return (int(year), int(month) if month else None, int(day) if day else None)

    # Textual: "15 mar 1975" / "15 march 1975" / "mar 1975"
    textual = re.match(r"^(?:(\d{1,2})\s+)?([a-z]{3,9})\s+(\d{4})$", text)
    if textual:
        day, month_name, year = textual.groups()
        month = _MONTHS.get(month_name[:3])
        if month:
            return (int(year), month, int(day) if day else None)

    # Bare year anywhere in the string
    bare = re.search(r"\b(\d{4})\b", text)
    if bare:
        return (int(bare.group(1)), None, None)

    return None


def dob_match(left: str | None, right: str | None) -> float:
    """Compare two DOBs at whatever precision they share.

    Returns 0.5 when either side is unknown, 1.0 when every component both
    sides declare agrees, and 0.0 on any contradiction. Comparing at shared
    precision means "1975" and "15 Mar 1975" agree rather than falsely
    contradicting each other on a string compare.
    """
    if not left or not right:
        return 0.5

    parsed_left, parsed_right = parse_dob(left), parse_dob(right)
    if parsed_left is None or parsed_right is None:
        return 1.0 if left.strip().lower() == right.strip().lower() else 0.0

    for component_left, component_right in zip(parsed_left, parsed_right):
        if component_left is not None and component_right is not None:
            if component_left != component_right:
                return 0.0
    return 1.0


# ---------------------------------------------------------------------------
# Semantic contextual similarity (playbook Stage 4)
# ---------------------------------------------------------------------------

# all-MiniLM-L6-v2 caps at 256 word-pieces and silently drops the remainder, so
# tokenising more than roughly that costs time and buys nothing. Real
# OpenSanctions contexts reach 48k characters (a semicolon-joined list of source
# datasets), which made the first query pay seconds to encode text the model
# discards. ~1000 chars comfortably covers 256 word-pieces.
MAX_CONTEXT_CHARS = 1000


@lru_cache(maxsize=100_000)
def _embed(text: str):
    """Encode one string, memoised and length-capped.

    Screening compares a single query context against every retrieved candidate,
    so encoding a pair per call re-encoded the query context once per candidate
    (~1,450 redundant encodes per query at real scale). Caching per string means
    the query is encoded once and candidate contexts are reused across queries.
    """
    return _semantic_model.encode(text[:MAX_CONTEXT_CHARS], convert_to_tensor=True)


def contextual_similarity(context_a: str | None, context_b: str | None) -> float:
    """Compute semantic similarity between two context strings.

    Uses sentence-transformers cosine similarity when available,
    otherwise falls back to fuzzy string matching.
    """
    if not context_a or not context_b:
        return 0.3  # unknown context — neutral score per playbook

    if _semantic_available and _semantic_model is not None:
        score = float(st_util.cos_sim(_embed(context_a), _embed(context_b)))
        # Clamp to [0, 1] since cosine sim can be slightly negative
        return max(0.0, min(1.0, score))

    # Fallback: fuzzy string matching
    return normalized_similarity(context_a, context_b)


# ---------------------------------------------------------------------------
# Classification and weighted scoring
# ---------------------------------------------------------------------------

def classify(score: float) -> str:
    if score >= CONFIRMED_THRESHOLD:
        return "CONFIRMED_MATCH"
    if score >= POSSIBLE_THRESHOLD:
        return "POSSIBLE_MATCH"
    return "LIKELY_FALSE_POSITIVE"


def weighted_match_score(component_scores: MatchComponentScores) -> float:
    return round(
        (
            0.30 * component_scores.name
            + 0.15 * component_scores.alias
            + 0.15 * component_scores.dob
            + 0.10 * component_scores.nationality
            + 0.15 * component_scores.company
            + 0.15 * component_scores.context
        ),
        4,
    )