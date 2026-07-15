"""Entity resolution pipeline with candidate retrieval and scoring."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from datetime import datetime, timezone

from .audit import ENTITY_MATCH_CALCULATED, emit
from .evidence import evidence_id_gen
from .schemas import EvidenceRecord, MatchComponentScores, SanctionedEntity
from .scoring import (
    POSSIBLE_THRESHOLD,
    alias_similarity,
    classify,
    contextual_similarity,
    country_match,
    dob_match,
    fuzzy_or_unknown_match,
    normalized_similarity,
    weighted_match_score,
)


# ---------------------------------------------------------------------------
# Candidate retrieval index (playbook Stage 1)
# ---------------------------------------------------------------------------

def candidate_retrieval_key(name: str | None) -> str:
    """Generate a 4-char alphanumeric prefix key for fast candidate lookup."""
    if not name:
        return ""
    normalized = "".join(character for character in name.lower() if character.isalnum())
    return normalized[:4]


class CandidateIndex:
    """Pre-indexed sanctions list for fast candidate retrieval.

    Groups entities by their 4-char prefix key so we only run expensive
    fuzzy matching against a small subset instead of the full list.
    """

    def __init__(self, entities: Iterable[SanctionedEntity] | None = None) -> None:
        self._index: dict[str, list[SanctionedEntity]] = defaultdict(list)
        self._all: list[SanctionedEntity] = []
        if entities:
            for entity in entities:
                self.add(entity)

    def add(self, entity: SanctionedEntity) -> None:
        """Add an entity to the index under its name key and each alias key.

        An entity is only added once per bucket: a name and an alias frequently
        share a prefix key ("Mohammad AL-RASHID" / "Mohammed AL RASHID" both key
        to "moha"), and a duplicated bucket entry would emit duplicate evidence
        records for a single real match.
        """
        self._all.append(entity)
        keys = {candidate_retrieval_key(entity.name)}
        keys.update(candidate_retrieval_key(alias) for alias in entity.aliases)
        for key in keys:
            if key:
                self._index[key].append(entity)

    def retrieve(self, query_name: str | None) -> list[SanctionedEntity]:
        """Return candidate entities blocked by prefix key on name or any token.

        A prefix miss returns nothing rather than the full list. Falling back to
        a full scan is harmless at sample scale but catastrophic against real
        OpenSanctions (~1.28M screenable entities): every miss would fuzzy-match
        the entire list, taking minutes per query.

        Tokens are blocked as well as the whole name so a reordered query
        ("Rashid, Mohammed" vs "Mohammed Al Rashid") still retrieves.
        """
        candidates: list[SanctionedEntity] = []
        seen: set[int] = set()
        for key in self._query_keys(query_name):
            for entity in self._index.get(key, ()):
                if id(entity) not in seen:
                    seen.add(id(entity))
                    candidates.append(entity)
        return candidates

    @staticmethod
    def _query_keys(name: str | None) -> set[str]:
        """Prefix keys to probe for a query: the whole name plus each token."""
        if not name:
            return set()
        keys = {candidate_retrieval_key(name)}
        keys.update(candidate_retrieval_key(token) for token in name.split())
        keys.discard("")
        return keys

    @property
    def size(self) -> int:
        return len(self._all)


# ---------------------------------------------------------------------------
# Component scoring (playbook Stages 2–4)
# ---------------------------------------------------------------------------

# Weight of the context component in weighted_match_score, i.e. the most that
# scoring context can ever add to a match.
CONTEXT_WEIGHT = 0.15

# Value used for context when the semantic call is pruned. Matches the
# "unknown context" default in contextual_similarity.
CONTEXT_UNKNOWN = 0.3


def build_component_scores(query: dict, candidate: SanctionedEntity) -> MatchComponentScores:
    """Score all six components, skipping context when it cannot change the verdict.

    Context is the only expensive component (a sentence-transformer encode). It
    can contribute at most CONTEXT_WEIGHT, so when the other five cannot reach
    POSSIBLE_THRESHOLD even with a perfect context score, the embedding is
    skipped. Pruned candidates stay below the threshold either way, so the
    classification is identical — only the wasted encode disappears.
    """
    scores = MatchComponentScores(
        name=normalized_similarity(query.get("name"), candidate.name),
        alias=alias_similarity(query.get("name", ""), candidate.aliases),
        dob=dob_match(query.get("dob"), candidate.dob),
        nationality=country_match(query.get("nationality"), candidate.nationality),
        company=fuzzy_or_unknown_match(query.get("company"), candidate.company),
        context=CONTEXT_UNKNOWN,
    )

    best_possible = weighted_match_score(scores) - CONTEXT_WEIGHT * CONTEXT_UNKNOWN + CONTEXT_WEIGHT
    if best_possible < POSSIBLE_THRESHOLD:
        return scores

    scores.context = contextual_similarity(query.get("context"), candidate.context)
    return scores


# ---------------------------------------------------------------------------
# Single-candidate resolution
# ---------------------------------------------------------------------------

def resolve_entity(query: dict, candidate: SanctionedEntity) -> EvidenceRecord:
    """Run the full scoring pipeline for one query–candidate pair."""
    component_scores = build_component_scores(query, candidate)
    match_score = weighted_match_score(component_scores)
    return EvidenceRecord(
        evidence_id=query.get("evidence_id") or evidence_id_gen.next_id(),
        entity_id=query.get("entity_id", "UNKNOWN"),
        matched_against=candidate.entity_id,
        match_score=match_score,
        component_scores=component_scores,
        classification=classify(match_score),
        source=candidate.source_list,
        retrieved_at=datetime.now(timezone.utc),
        metadata={"candidate_name": candidate.name},
    )


# ---------------------------------------------------------------------------
# Batch resolution with candidate retrieval (playbook §7 integration)
# ---------------------------------------------------------------------------

DEFAULT_MATCH_LIMIT = 25


def resolve_against_candidates(
    query: dict,
    index: CandidateIndex,
    limit: int | None = DEFAULT_MATCH_LIMIT,
) -> list[EvidenceRecord]:
    """Resolve a KYC entity against all candidates from the index.

    Uses the CandidateIndex for fast pre-filtering, then scores each
    candidate and returns matches sorted by score (highest first).
    Only returns CONFIRMED_MATCH and POSSIBLE_MATCH results.

    `limit` keeps the top N. Against the real lists a common given name yields
    ~70 weak POSSIBLE_MATCHes on the 0.55 threshold alone, which buries the real
    hit and floods Part 3's risk formula. Pass None to keep every match.
    """
    candidates = index.retrieve(query.get("name"))
    results: list[EvidenceRecord] = []

    for candidate in candidates:
        record = resolve_entity(query, candidate)
        if record.classification in {"CONFIRMED_MATCH", "POSSIBLE_MATCH"}:
            results.append(record)

    results.sort(key=lambda r: r.match_score, reverse=True)
    returned = results[:limit] if limit is not None else results

    # Playbook §7 -> Part 1. Emitted per *returned* match rather than per
    # candidate scored: a single query fuzzy-matches ~1,500 candidates, and
    # logging every rejection would bury the decisions that actually matter.
    # The candidates_scored count preserves the denominator.
    for record in returned:
        emit(
            ENTITY_MATCH_CALCULATED,
            record.entity_id,
            reason=record.classification,
            new_value=record.match_score,
            metadata={
                "evidence_id": record.evidence_id,
                "matched_against": record.matched_against,
                "source": record.source,
                "candidates_scored": len(candidates),
                "component_scores": record.component_scores.model_dump(),
            },
        )

    return returned
