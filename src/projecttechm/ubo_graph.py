from __future__ import annotations

from collections.abc import Iterable

import networkx as nx

from .resolution import CandidateIndex, resolve_against_candidates
from .schemas import EntityRecord, SanctionedEntity

# Identifiers a graph node may carry in `metadata` that sharpen resolution.
# Dropping these costs the hidden-UBO showcase ~0.25 of match score.
_QUERY_FIELDS = ("dob", "nationality", "company")


def node_to_query(graph: nx.DiGraph, node: str) -> dict:
    """Build a resolution query from a graph node.

    `add_entity` parks everything except entity_id/name/context under `metadata`,
    so DOB, nationality and company live there — they must be lifted back out or
    the scorer treats each as unknown.
    """
    data = graph.nodes[node]
    metadata = data.get("metadata") or {}
    query = {
        "entity_id": data.get("entity_id", node),
        "name": data.get("name", node),
        "context": data.get("context"),
    }
    for field in _QUERY_FIELDS:
        value = data.get(field) or metadata.get(field)
        if value:
            query[field] = value
    return query


def find_sanctioned_in_chain(
    graph: nx.DiGraph,
    root_entity_id: str,
    sanctions: Iterable[SanctionedEntity] | CandidateIndex,
    max_depth: int = 5,
) -> list[dict]:
    """Walk every ownership path below a root and resolve each node.

    Reports the *best* match per node, not the first one over the threshold —
    scanning in list order made the reported hit arbitrary. Accepts a prebuilt
    CandidateIndex to avoid re-indexing (and to avoid scanning the whole
    sanctions list per node).
    """
    index = sanctions if isinstance(sanctions, CandidateIndex) else CandidateIndex(sanctions)
    findings: list[dict] = []

    for node in nx.descendants(graph, root_entity_id):
        try:
            path = nx.shortest_path(graph, root_entity_id, node)
        except nx.NetworkXNoPath:
            continue
        if len(path) - 1 > max_depth:
            continue

        matches = resolve_against_candidates(node_to_query(graph, node), index, limit=1)
        if matches:
            findings.append(
                {
                    "node": node,
                    "match": matches[0].model_dump(),
                    "ownership_path": path,
                }
            )

    findings.sort(key=lambda f: f["match"]["match_score"], reverse=True)
    return findings


def add_entity(graph: nx.DiGraph, entity: EntityRecord) -> None:
    graph.add_node(entity.entity_id, name=entity.name, context=entity.context, metadata=entity.metadata)
