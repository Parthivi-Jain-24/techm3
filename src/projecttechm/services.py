"""Service layer: loads reference data once and exposes the playbook §7 contracts.

This sits between the pure library modules (resolution, adverse_media, ubo_graph)
and the FastAPI transport in `api.py`. It owns process-wide state: the sanctions
CandidateIndex, the client book, the UBO graphs, and the adverse-media findings store.
"""

from __future__ import annotations

import os
import re
import threading
from pathlib import Path
from typing import Any

import networkx as nx

from .adverse_media import build_finding, sanitize_article
from .audit import (
    ADVERSE_MEDIA_AGENT_RUN,
    PROMPT_INJECTION_DETECTED,
    emit,
)
from .egress import current_policy as egress_policy
from .llm_agent import analyze as llm_analyze, is_llm_available, provider_info
from .data_loader import (
    load_articles,
    load_clients,
    load_ofac_sdn,
    load_opensanctions,
    load_ubo_structure,
)
from .resolution import DEFAULT_MATCH_LIMIT, CandidateIndex, resolve_against_candidates
from .schemas import AdverseMediaFinding, Claim, EvidenceRecord, SanctionedEntity
from .scoring import is_semantic_available, warm_semantic_model
from .ubo_graph import add_entity, find_sanctioned_in_chain

# Sentences containing these terms are treated as candidate allegations by the
# heuristic extractor. This is NOT the playbook's LLM extraction pass — see
# `ALLEGATION_TERMS` usage in `_extract_claims_heuristic`.
ALLEGATION_TERMS = (
    "alleged", "allegedly", "accused", "investigation", "investigators",
    "sanctioned", "sanctions", "laundering", "fraud", "charged", "arrested",
    "seized", "frozen", "probe", "violation", "evasion", "illicit", "shell",
)

EXTRACTION_METHOD = "heuristic_keyword"


# Full OpenSanctions is ~1.32M rows / 488 MB, of which ~1.28M are KYC-screenable.
# Measured full load: ~23s and ~1.1 GB resident including the candidate index
# (~624 bytes/entity, down from ~1,617 before SanctionedEntity became a slotted
# dataclass).
#
# Default to loading all of it. Screening a subset by default is the wrong
# default for a compliance system: a bounded index cannot find a party it never
# indexed, and "we only screened part of the list" is not a defensible answer to
# a regulator. The cost is ~21s of extra startup, paid once per process.
#
# For fast `uvicorn --reload` iteration, set PROJECTTECHM_OPENSANCTIONS_LIMIT to
# a row cap (200000 loads in ~2s). Any cap is disclosed, never silent:
# /health reports sanctions_coverage_complete=false and marks the source
# truncated. Set 0/none to force full explicitly.
DEFAULT_OPENSANCTIONS_LIMIT: int | None = None

# Suggested cap for dev iteration, referenced in the README and error messages.
DEV_OPENSANCTIONS_LIMIT = 200_000

# The playbook's §9 regression cases and the hidden-UBO showcase are synthetic:
# "Mohammed Al Rashid" / CUST-2041 / ABC Holdings appear only in the committed
# sample fixtures, never in real OFAC or OpenSanctions. Loading real data alone
# silently evicts the demo; loading fixtures alone hides real-world scale. Modes:
#   "both"   - real lists plus the demo fixtures (default; demo works at scale)
#   "real"   - real lists only (what production screening would see)
#   "sample" - fixtures only (fast, deterministic; used by the test suite)
SANCTIONS_MODES = ("both", "real", "sample")
DEFAULT_SANCTIONS_MODE = "both"

# Fixture entities are tagged so a synthetic record can never be mistaken for a
# genuine sanctions listing in evidence handed to Part 3 / Part 4.
FIXTURE_SOURCE_SUFFIX = " (SAMPLE FIXTURE)"


def _sanctions_mode() -> str:
    raw = (os.environ.get("PROJECTTECHM_SANCTIONS_MODE") or DEFAULT_SANCTIONS_MODE).strip().lower()
    return raw if raw in SANCTIONS_MODES else DEFAULT_SANCTIONS_MODE


def _default_data_dir() -> Path:
    override = os.environ.get("PROJECTTECHM_DATA_DIR")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[2] / "data"


def _opensanctions_limit() -> int | None:
    raw = os.environ.get("PROJECTTECHM_OPENSANCTIONS_LIMIT")
    if raw is None:
        return DEFAULT_OPENSANCTIONS_LIMIT
    if raw.strip().lower() in {"0", "none", "all", ""}:
        return None
    try:
        return int(raw)
    except ValueError:
        return DEFAULT_OPENSANCTIONS_LIMIT


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text.replace("\n", " "))
    return [p.strip() for p in parts if p.strip()]


def _extract_claims_heuristic(article: str) -> list[Claim]:
    """Pull allegation-bearing sentences straight out of the source text.

    Claims are verbatim source sentences, so `supported` is True by construction.
    This deliberately does not call an LLM; the playbook's extraction + guard
    passes are not implemented yet.
    """
    claims: list[Claim] = []
    for sentence in _split_sentences(article):
        lowered = sentence.lower()
        hits = sum(1 for term in ALLEGATION_TERMS if term in lowered)
        if hits:
            claims.append(
                Claim(
                    claim=sentence,
                    supported=True,
                    confidence=round(min(0.5 + 0.1 * hits, 0.9), 2),
                )
            )
    return claims


class KycRegistry:
    """Process-wide reference data and the playbook §7 integration contracts."""

    def __init__(self, data_dir: str | Path | None = None) -> None:
        self.data_dir = Path(data_dir) if data_dir else _default_data_dir()
        self._lock = threading.Lock()
        self._loaded = False

        self.sanctions: list[SanctionedEntity] = []
        self.index: CandidateIndex = CandidateIndex()
        self.sources: dict[str, dict[str, Any]] = {}
        self.mode: str = _sanctions_mode()
        self.clients: list[dict[str, Any]] = []
        self._clients_by_id: dict[str, dict[str, Any]] = {}
        self.graphs: dict[str, nx.DiGraph] = {}
        self.articles: dict[str, str] = {}
        self._media_store: dict[str, list[AdverseMediaFinding]] = {}

    # -- loading ----------------------------------------------------------

    def load(self) -> None:
        """Load every dataset that is present. Missing files are skipped, not fatal."""
        with self._lock:
            if self._loaded:
                return

            self._load_sanctions()
            self.index = CandidateIndex(self.sanctions)

            clients_csv = self.data_dir / "clients_with_fatf_ofac.csv"
            if clients_csv.exists():
                self.clients = load_clients(clients_csv)
                self._clients_by_id = {c["entity_id"]: c for c in self.clients}

            ubo_dir = self.data_dir / "ubo"
            if ubo_dir.exists():
                for path in sorted(ubo_dir.glob("*.json")):
                    entities, edges = load_ubo_structure(path)
                    graph = nx.DiGraph()
                    for entity in entities:
                        add_entity(graph, entity)
                    for edge in edges:
                        graph.add_edge(edge.owner_id, edge.owned_id, percentage=edge.percentage)
                    self.graphs[path.stem] = graph

            articles_dir = self.data_dir / "articles"
            if articles_dir.exists():
                self.articles = {
                    a["filename"]: a["content"] for a in load_articles(articles_dir)
                }

            # Pay torch's first-forward-pass cost here, not on the first query.
            warm_semantic_model()

            self._loaded = True

    def _load_sanctions(self) -> None:
        """Load OFAC SDN and OpenSanctions per the configured mode."""
        sanctions_dir = self.data_dir / "sanctions"
        self.mode = _sanctions_mode()
        want_real = self.mode in {"both", "real"}
        want_fixtures = self.mode in {"both", "sample"}

        real_sdn = sanctions_dir / "ofac_sdn.csv"
        real_alt = sanctions_dir / "ofac_alt.csv"
        real_os = sanctions_dir / "opensanctions_targets.csv"

        if want_real and real_sdn.exists():
            loaded = load_ofac_sdn(real_sdn, real_alt if real_alt.exists() else None)
            self.sanctions.extend(loaded)
            self.sources["ofac_sdn"] = {
                "file": real_sdn.name,
                "real_data": True,
                "entities": len(loaded),
                "aliases_file": real_alt.name if real_alt.exists() else None,
                "truncated": False,
            }

        if want_real and real_os.exists():
            limit = _opensanctions_limit()
            loaded = load_opensanctions(real_os, limit=limit)
            self.sanctions.extend(loaded)
            self.sources["opensanctions"] = {
                "file": real_os.name,
                "real_data": True,
                "entities": len(loaded),
                "limit": limit,
                # Never let a bounded load look like full coverage.
                "truncated": limit is not None and len(loaded) >= limit,
            }

        if want_fixtures:
            self._load_fixtures(sanctions_dir)

    def _load_fixtures(self, sanctions_dir: Path) -> None:
        """Load the synthetic demo fixtures, tagged so they can't pass as real."""
        fixture_sdn = sanctions_dir / "sample_ofac_sdn.csv"
        fixture_alt = sanctions_dir / "sample_ofac_alt.csv"
        fixture_os = sanctions_dir / "sample_opensanctions.csv"

        fixtures: list[SanctionedEntity] = []
        if fixture_sdn.exists():
            fixtures.extend(
                load_ofac_sdn(fixture_sdn, fixture_alt if fixture_alt.exists() else None)
            )
        if fixture_os.exists():
            fixtures.extend(load_opensanctions(fixture_os))

        for entity in fixtures:
            if not entity.source_list.endswith(FIXTURE_SOURCE_SUFFIX):
                entity.source_list += FIXTURE_SOURCE_SUFFIX

        self.sanctions.extend(fixtures)
        if fixtures:
            self.sources["demo_fixtures"] = {
                "file": "sample_*.csv",
                "real_data": False,
                "entities": len(fixtures),
                "truncated": False,
                "note": "Synthetic playbook §9 / hidden-UBO demo entities, not real listings",
            }

    # -- lookups ----------------------------------------------------------

    def normalize_customer_id(self, customer_id: str) -> str:
        """Accept both `7` and `CLIENT-7`."""
        if customer_id in self._clients_by_id:
            return customer_id
        prefixed = f"CLIENT-{customer_id}"
        return prefixed if prefixed in self._clients_by_id else customer_id

    def get_client(self, customer_id: str) -> dict[str, Any] | None:
        return self._clients_by_id.get(self.normalize_customer_id(customer_id))

    # -- playbook §7 contract: to Part 3 (Risk Intelligence) --------------

    def screen(
        self,
        query: dict[str, Any],
        limit: int | None = DEFAULT_MATCH_LIMIT,
    ) -> list[EvidenceRecord]:
        """Resolve an arbitrary KYC entity against the sanctions index."""
        return resolve_against_candidates(query, self.index, limit=limit)

    def get_sanctions_matches(
        self,
        customer_id: str,
        limit: int | None = DEFAULT_MATCH_LIMIT,
    ) -> list[EvidenceRecord]:
        """Playbook §7 contract for Part 3. Raises KeyError on unknown customer."""
        client = self.get_client(customer_id)
        if client is None:
            raise KeyError(customer_id)
        return self.screen(client, limit=limit)

    def get_adverse_media(self, customer_id: str) -> list[AdverseMediaFinding]:
        """Playbook §7 contract for Part 3.

        Returns findings previously produced by `analyze_article` for this
        customer. Empty until an article has been analyzed against them.
        """
        return list(self._media_store.get(self.normalize_customer_id(customer_id), []))

    # -- adverse media ----------------------------------------------------

    def _extract_claims_llm(self, article: str) -> tuple[list[Claim], dict[str, Any]]:
        """Run the playbook §4 two-pass agent; return guard-upheld claims only."""
        result = llm_analyze(article)
        claims = [
            Claim(
                claim=c["claim"],
                supported=True,  # only guard-upheld claims reach here
                confidence=float(c.get("confidence", 0.5)),
            )
            for c in result["claims"]
        ]
        return claims, {
            "extraction_method": result["extraction_method"],
            # Which model produced the claim is provenance: Part 4 cites these,
            # and a claim from a 8B local model is not the same evidence as one
            # from a frontier model.
            "provider": result["provider"],
            "model": result["model"],
            "claims_dropped_by_guard": len(result["dropped_claims"]),
            "entities": result["entities"],
            "injection_suspected": result["injection_suspected"],
            "injection_note": result.get("injection_note", ""),
        }

    def analyze_article(
        self,
        entity_id: str,
        article: str,
        source_url: str,
        use_llm: bool | None = None,
    ) -> AdverseMediaFinding:
        """Sanitize an article, flag injection attempts, and extract claims.

        The article is treated strictly as untrusted data. If an injection
        attempt is detected the claims are still extracted from the source
        text, but the finding is flagged so downstream consumers can quarantine it.
        """
        _, injection_detected, details = sanitize_article(article)

        if use_llm is None:
            use_llm = is_llm_available()

        extra: dict[str, Any] = {}
        if use_llm:
            try:
                claims, extra = self._extract_claims_llm(article)
                if extra.get("injection_suspected") and not injection_detected:
                    # The model caught a phrasing the pattern matcher missed.
                    injection_detected = True
                    details = (
                        f"Suspected prompt injection (LLM-detected); "
                        f"treated as data, not instructions. {extra.get('injection_note', '')}"
                    ).strip()
            except Exception as exc:  # noqa: BLE001 - never fail closed on the LLM
                claims = _extract_claims_heuristic(article)
                extra = {
                    "extraction_method": EXTRACTION_METHOD,
                    "llm_error": f"{type(exc).__name__}: {exc}",
                }
        else:
            claims = _extract_claims_heuristic(article)
            extra = {
                "extraction_method": EXTRACTION_METHOD,
                "llm_extraction": "unavailable",
                "guard_pass": "unavailable",
            }

        finding = build_finding(entity_id, source_url, claims, injection_detected, details)
        finding.metadata.update(extra)
        finding.metadata.setdefault("extraction_method", EXTRACTION_METHOD)
        self._media_store.setdefault(entity_id, []).append(finding)

        # Playbook §7 -> Part 1.
        emit(
            ADVERSE_MEDIA_AGENT_RUN,
            entity_id,
            reason=f"Analyzed article; {len(claims)} claim(s) extracted",
            metadata={
                "evidence_id": finding.evidence_id,
                "source_url": source_url,
                "claims": len(claims),
                "extraction_method": EXTRACTION_METHOD,
            },
        )
        if injection_detected:
            emit(
                PROMPT_INJECTION_DETECTED,
                entity_id,
                reason=details,
                metadata={
                    "evidence_id": finding.evidence_id,
                    "source_url": source_url,
                    "action_taken": "article treated as data; no instruction followed",
                },
            )

        return finding

    # -- UBO --------------------------------------------------------------

    def trace_ubo(
        self,
        structure: str,
        root_entity_id: str | None = None,
        max_depth: int = 5,
    ) -> dict[str, Any]:
        """Walk an ownership graph and resolve every downstream node."""
        graph = self.graphs.get(structure)
        if graph is None:
            raise KeyError(structure)

        if root_entity_id is None:
            roots = [n for n, deg in graph.in_degree() if deg == 0]
            if not roots:
                raise ValueError(f"{structure} has no root node")
            root_entity_id = roots[0]
        elif root_entity_id not in graph:
            raise KeyError(root_entity_id)

        findings = find_sanctioned_in_chain(graph, root_entity_id, self.index, max_depth)
        return {
            "structure": structure,
            "root_entity_id": root_entity_id,
            "nodes_traversed": len(nx.descendants(graph, root_entity_id)),
            "findings": findings,
        }

    # -- health -----------------------------------------------------------

    def stats(self) -> dict[str, Any]:
        return {
            "data_dir": str(self.data_dir),
            "sanctions_mode": self.mode,
            "sanctions_indexed": self.index.size,
            "sanctions_sources": self.sources,
            "sanctions_coverage_complete": not any(
                s.get("truncated") for s in self.sources.values()
            ),
            "clients_loaded": len(self.clients),
            "ubo_structures": sorted(self.graphs),
            "articles": sorted(self.articles),
            "semantic_matching_available": is_semantic_available(),
            "llm_adverse_media_available": is_llm_available(),
            "llm_provider": provider_info(),
            # What a third-party model is permitted to receive. The agent sends
            # public article text only; this is the enforcement, not the promise.
            "llm_egress_policy": egress_policy(),
        }


_registry: KycRegistry | None = None
_registry_lock = threading.Lock()


def get_registry() -> KycRegistry:
    """Return the process-wide registry, loading data on first call."""
    global _registry
    with _registry_lock:
        if _registry is None:
            _registry = KycRegistry()
            _registry.load()
        return _registry


def reset_registry() -> None:
    """Drop the cached registry. For tests."""
    global _registry
    with _registry_lock:
        _registry = None
