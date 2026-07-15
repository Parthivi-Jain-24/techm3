"""Adapter from Part 2's internal records to the canonical integration contracts.

Part 2 computes with `EvidenceRecord` (see schemas.py) — component scores, a
0-1 match score, our own classification strings. Parts 3 and 4 consume
`EntityIntelligenceResult` from `app.schemas.entity_intelligence`, which Part 1
owns and has already implemented. This module is the seam.

Why a translation layer rather than changing either side: `EvidenceRecord` is
what the resolver naturally produces and what our 300+ tests pin;
`EntityIntelligenceResult` is a negotiated cross-workstream contract that three
other workstreams code against. Neither should bend to the other, and a contract
whose field names drift with one team's refactor is not a contract.

Four things genuinely differ, and each is a place a silent bug would live:

  * Scale — our match_score is 0-1, `Score` is 0-100. A 0.81 written straight
    into a 0-100 field is not "0.81 confidence", it is 0.81/100 — a confirmed
    match rendered as near-zero. Multiply, do not pass through.
  * Vocabulary — our classification strings are not their enum values, and
    theirs has five members to our three.
  * Semantics — `match_confidence` is confidence in IDENTITY RESOLUTION, not
    risk. Their schema deliberately carries no risk field; we must not smuggle
    one in.
  * Provenance — they split `source` into source_type/source_name; we carry one
    string, sometimes tagged "(SAMPLE FIXTURE)".
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .scoring import CONFIRMED_THRESHOLD, POSSIBLE_THRESHOLD

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .schemas import AdverseMediaFinding, EvidenceRecord

# Their Score is 0-100; ours is 0-1.
SCORE_SCALE = 100.0

# Any component scoring at or above this counts as having corroborated the
# match, and is named in `matched_attributes` for downstream explainability.
# 0.5 is the "unknown" value used by dob/nationality/company, so the bar sits
# above it — an unknown attribute corroborates nothing.
CORROBORATION_FLOOR = 0.55

# Marker added by the registry to synthetic demo entities. It must never reach
# a downstream consumer as though it were an authoritative source name.
FIXTURE_MARKER = "(SAMPLE FIXTURE)"


def _decision_for(record: EvidenceRecord) -> str:
    """Map our classification onto their EntityMatchDecision.

    Their contract states a name match ALONE must never yield confirmed_match —
    identity has to be corroborated by other attributes. We enforce that here
    rather than trusting the caller: a record can clear 0.85 on name and alias
    similarity alone (both derive from the same string), and that is exactly the
    "John Smith the director vs John Smith the criminal" case the whole pipeline
    exists to prevent. Such a record is downgraded to needs_review.
    """
    score = record.match_score
    scores = record.component_scores

    if score >= CONFIRMED_THRESHOLD:
        corroborating = [
            value
            for field, value in (
                ("dob", scores.dob),
                ("nationality", scores.nationality),
                ("company", scores.company),
                ("context", scores.context),
            )
            if value >= CORROBORATION_FLOOR
        ]
        if not corroborating:
            # High score, but nothing beyond the name agrees.
            return "needs_review"
        return "confirmed_match"

    if score >= POSSIBLE_THRESHOLD:
        return "likely_match"
    return "likely_false_positive"


def _matched_attributes(record: EvidenceRecord) -> list[str]:
    """Which attributes actually corroborated the match.

    Downstream explainability: Part 3 shows the reviewer *why* something
    matched, and "name + dob + country" is an answer where 0.83 is not.
    """
    scores = record.component_scores
    return [
        name
        for name, value in (
            ("name", scores.name),
            ("alias", scores.alias),
            ("dob", scores.dob),
            ("nationality", scores.nationality),
            ("company", scores.company),
            ("context", scores.context),
        )
        if value >= CORROBORATION_FLOOR
    ]


def _split_source(source: str) -> tuple[str, str]:
    """Split our single source string into their source_type / source_name.

    A fixture's marker is preserved in source_name rather than stripped: a
    reviewer looking at a synthetic record must be able to tell. Dropping it
    here would be the one edit that lets a demo entity pass as a real listing.
    """
    name = source.strip()
    lowered = name.lower()
    if "ofac" in lowered:
        source_type = "sanctions"
    elif "opensanction" in lowered or "sanction" in lowered:
        source_type = "sanctions"
    elif "pep" in lowered:
        source_type = "watchlist"
    else:
        source_type = "watchlist"
    return source_type, name


def evidence_to_result(record: EvidenceRecord) -> dict[str, Any]:
    """Convert one EvidenceRecord to an EntityIntelligenceResult payload.

    Returns a plain dict rather than the pydantic model so this module stays
    importable without `app` on the path — Part 2 runs standalone, and a hard
    import of another workstream's package would make our 300+ tests depend on
    theirs. `to_entity_intelligence_result` validates when `app` is available.
    """
    source_type, source_name = _split_source(record.source)
    return {
        "result_id": record.evidence_id,
        "client_id": record.entity_id,
        "source_type": source_type,
        "source_name": source_name,
        "matched_entity_name": record.metadata.get("candidate_name"),
        # 0-1 -> 0-100. Rounded to 2dp: their Score is a float, and 81.0
        # reads as a confidence where 80.99999999999999 reads as a bug.
        "match_confidence": round(record.match_score * SCORE_SCALE, 2),
        "decision": _decision_for(record),
        "matched_attributes": _matched_attributes(record),
        "evidence_references": [record.evidence_id],
        "evaluated_at": record.retrieved_at,
    }


def adverse_media_to_result(finding: AdverseMediaFinding) -> dict[str, Any]:
    """Convert an AdverseMediaFinding to an EntityIntelligenceResult payload.

    Adverse media resolves nothing about identity — it reports what an article
    said about a name. So `match_confidence` here is the extractor's confidence
    in its own claims, and the decision is never `confirmed_match`: a news
    article is not identity corroboration, and a pipeline that treats it as such
    would confirm a customer against a namesake in the news.

    A finding whose article carried a prompt-injection attempt is marked
    needs_review regardless of claim confidence — its content is not trustworthy
    input to an automated decision.
    """
    claims = finding.extracted_claims
    confidence = (
        max((c.confidence for c in claims), default=0.0) * SCORE_SCALE if claims else 0.0
    )

    if finding.injection_attempt_detected:
        decision = "needs_review"
    elif not claims:
        decision = "no_match"
    else:
        decision = "likely_match"

    return {
        "result_id": finding.evidence_id,
        "client_id": finding.entity_id,
        "source_type": "adverse_media",
        "source_name": finding.source_url or "adverse_media",
        "matched_entity_name": None,
        "match_confidence": round(confidence, 2),
        "decision": decision,
        "matched_attributes": ["adverse_media"] if claims else [],
        "evidence_references": [finding.evidence_id],
        "evaluated_at": finding.retrieved_at,
    }


def to_entity_intelligence_result(record: EvidenceRecord):
    """Validated `EntityIntelligenceResult`, when Part 1's package is importable.

    Raises ImportError if `app.schemas` is absent — callers running Part 2
    standalone should use `evidence_to_result` and get the dict.
    """
    from app.schemas.entity_intelligence import (  # noqa: PLC0415 - optional cross-workstream dep
        EntityIntelligenceResult,
    )

    return EntityIntelligenceResult(**evidence_to_result(record))


# ---------------------------------------------------------------------------
# Part 3 (risk_engine) signal shape
#
# risk_engine.scoring consumes a DIFFERENT shape from Part 1's contract, on a
# DIFFERENT scale, and the two disagree:
#
#   Part 1's EntityIntelligenceResult.match_confidence : Score = 0-100
#   risk_engine.scoring.make_factor                    : clamp(confidence, 0, 1)
#
# Feeding Part 1's contract straight into Part 3 clamps every value >= 1.0 to
# 1.0, so a 0.31 likely-false-positive (31.0) and a 0.94 confirmed match (94.0)
# both score full points. Every sanctions hit maxes out risk scoring, and the
# result looks plausible on a dashboard — a silent failure, which is the worst
# kind for a compliance system.
#
# Neither side is wrong on its own terms and neither is ours to redefine, so the
# conflict is bridged here and reported to both owners. Part 3 also wants keys
# Part 1's contract has no place for (`has_match`, `relationship`), which is why
# this cannot simply be `evidence_to_result` with a divided score.
# ---------------------------------------------------------------------------

#: risk_engine.scoring.UBO_RELATIONSHIPS — a match on one of these scores as an
#: ownership-chain hit (12 pts) rather than a direct hit (18 pts).
UBO_RELATIONSHIPS = frozenset(
    {"ubo", "beneficial owner", "director", "signatory", "shareholder"}
)

#: risk_engine.scoring awards `trusted_sanctions_source` only for these exact
#: lowercase strings. Our source_list values must be normalised onto them or the
#: bonus is silently never granted.
TRUSTED_SOURCES = {"ofac sdn", "opensanctions"}


def _normalize_source_for_risk(source: str) -> str:
    """Map our source_list onto the strings risk_engine tests for.

    A fixture keeps its marker and therefore will NOT match TRUSTED_SOURCES —
    that is intended. A synthetic record should not earn an authoritative-source
    bonus in a risk score.
    """
    lowered = source.strip().lower()
    if FIXTURE_MARKER.lower() in lowered:
        return lowered
    if "ofac" in lowered:
        return "ofac sdn"
    if "opensanction" in lowered or "us_ofac" in lowered:
        return "opensanctions"
    return lowered


def to_risk_sanctions_signal(
    record: EvidenceRecord,
    relationship: str | None = None,
) -> dict[str, Any]:
    """Build the `sanctions` section of a risk_engine assess() payload.

    `relationship` describes how the matched party relates to the customer. Pass
    one of UBO_RELATIONSHIPS for a hit found through the ownership graph — Part 3
    scores those as an ownership-chain match. Omit it for a direct hit on the
    customer.

    Note the scale: `match_confidence` here is 0-1, NOT the 0-100 of Part 1's
    contract. That is deliberate — see the module comment above.
    """
    signal: dict[str, Any] = {
        "has_match": record.classification in {"CONFIRMED_MATCH", "POSSIBLE_MATCH"},
        # 0-1, matching risk_engine's clamp. Do not "fix" this to 0-100.
        "match_confidence": record.match_score,
        "source": _normalize_source_for_risk(record.source),
        "evidence_id": record.evidence_id,
        "matched_entity": record.metadata.get("candidate_name"),
    }
    if relationship:
        signal["relationship"] = relationship.strip().lower()
    return signal


def to_risk_media_signal(finding: AdverseMediaFinding) -> dict[str, Any]:
    """Build the `adverse_media` section of a risk_engine assess() payload.

    risk_engine gates on `negative_news_found` and reads `confidence` (0-1),
    `severity`, `source`, `source_count`, `days_since_event`.

    An article carrying a prompt-injection attempt reports no negative news. Its
    content is attacker-influenced, and letting it raise a risk score would hand
    an attacker a lever on the score — the inverse of the attack the guard
    already blocks, and just as bad.
    """
    claims = finding.extracted_claims
    if finding.injection_attempt_detected or not claims:
        return {"negative_news_found": False, "evidence_id": finding.evidence_id}

    return {
        "negative_news_found": True,
        # 0-1, matching risk_engine's clamp.
        "confidence": max(c.confidence for c in claims),
        "source": finding.source_url or "adverse_media",
        "source_count": 1,
        "evidence_id": finding.evidence_id,
    }
