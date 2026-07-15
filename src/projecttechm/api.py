"""FastAPI transport for the entity-intelligence engine.

Run:
    uvicorn projecttechm.api:app --reload
    # then open http://127.0.0.1:8000/docs
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Path as PathParam, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from .audit import AuditEvent, InMemoryAuditSink, get_audit_sink
from .resolution import DEFAULT_MATCH_LIMIT
from .schemas import AdverseMediaFinding, EvidenceRecord
from .services import get_registry


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class ScreenRequest(BaseModel):
    """A KYC entity to screen against the sanctions lists.

    Only `name` is required; every other field improves scoring accuracy.
    Missing dob/nationality score 0.5 (neutral) rather than penalising.
    """

    entity_id: str = "ADHOC-001"
    name: str
    dob: str | None = None
    nationality: str | None = None
    company: str | None = None
    context: str | None = None

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "entity_id": "CUST-2041",
                    "name": "Mohammed Al Rashid",
                    "dob": "1975",
                    "nationality": "UAE",
                    "company": "ABC Holdings",
                    "context": "Director at ABC Holdings",
                }
            ]
        }
    }


class AdverseMediaRequest(BaseModel):
    """Analyze an article for adverse media. Supply `article` or `article_name`."""

    entity_id: str = "CUST-2041"
    article: str | None = Field(None, description="Raw article text (untrusted data)")
    article_name: str | None = Field(
        None, description="Filename of a bundled demo article, e.g. adversarial_article.txt"
    )
    source_url: str = "https://example.test/article"

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "entity_id": "CUST-2041",
                    "article_name": "adversarial_article.txt",
                    "source_url": "https://example.test/golden-crescent",
                }
            ]
        }
    }


class UboTraceRequest(BaseModel):
    structure: str = "showcase_structure"
    root_entity_id: str | None = None
    max_depth: int = 5


# ---------------------------------------------------------------------------
# Response models
#
# These exist so /docs publishes a real contract. Returning a bare dict renders
# as {"additionalProp1": {}} in Swagger, which tells a reviewer — and Part 3/4,
# who build against these — nothing at all.
# ---------------------------------------------------------------------------

class SanctionsSource(BaseModel):
    """Provenance for one loaded list."""

    file: str
    real_data: bool = Field(description="False for synthetic demo fixtures")
    entities: int
    truncated: bool = Field(description="True when a row limit capped the load")
    limit: int | None = None
    aliases_file: str | None = None
    note: str | None = None


class HealthResponse(BaseModel):
    status: str
    data_dir: str
    sanctions_mode: str = Field(description="both | real | sample")
    sanctions_indexed: int
    sanctions_sources: dict[str, SanctionsSource]
    sanctions_coverage_complete: bool = Field(
        description="False when any list was truncated — screening is not exhaustive"
    )
    clients_loaded: int
    ubo_structures: list[str]
    articles: list[str]
    semantic_matching_available: bool = Field(
        description="False means contextual_similarity silently falls back to fuzzy"
    )
    llm_adverse_media_available: bool = Field(
        description="False means adverse media falls back to the keyword heuristic"
    )
    llm_provider: dict[str, Any] = Field(
        description="Resolved LLM backend — provider, model, endpoint"
    )
    llm_egress_policy: str = Field(
        description="block | redact | allow — what may be sent to a third-party model"
    )


class CustomerSummary(BaseModel):
    entity_id: str
    name: str
    country: str
    sector: str
    pep_flag: int
    sanctions_flag: int


class CustomerPage(BaseModel):
    total: int
    limit: int
    offset: int
    customers: list[CustomerSummary]


class UboStructureInfo(BaseModel):
    name: str
    nodes: int
    edges: int
    roots: list[str]


class UboStructureList(BaseModel):
    structures: list[UboStructureInfo]


class UboFinding(BaseModel):
    node: str
    match: EvidenceRecord
    ownership_path: list[str] = Field(
        description="Root to matched node — how the risk is hidden"
    )


class UboTraceResponse(BaseModel):
    structure: str
    root_entity_id: str
    nodes_traversed: int
    findings: list[UboFinding] = Field(description="Best match per node, highest score first")


class AuditEventPage(BaseModel):
    total_emitted: int
    dropped: int = Field(description="Events aged out of the bounded sink")
    returned: int
    sink: str = Field(description="Sink implementation; Part 1 swaps this out")
    events: list[AuditEvent]


class AuditVerifyResponse(BaseModel):
    valid: bool
    events_checked: int
    broken_at: str | None = Field(description="event_id where the chain first breaks")
    reason: str | None = None
    verified_from_genesis: bool = Field(
        description="False when older events aged out, so the chain is only checked from the oldest retained entry"
    )


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    get_registry()  # load reference data before serving traffic
    yield


app = FastAPI(
    title="ProjectTechM — Entity Intelligence API",
    version="0.1.0",
    description=(
        "Sanctions screening, adverse-media analysis with prompt-injection defenses, "
        "and hidden-UBO ownership tracing for the Continuous KYC Autonomous Auditor."
    ),
    lifespan=lifespan,
)


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    """Send the base URL to the docs rather than a bare 404."""
    return RedirectResponse(url="/docs")


@app.get("/health", response_model=HealthResponse, tags=["ops"])
def health() -> dict[str, Any]:
    """Loaded dataset counts and whether the semantic matcher is active."""
    return {"status": "ok", **get_registry().stats()}


# -- screening --------------------------------------------------------------

@app.post("/screen", response_model=list[EvidenceRecord], tags=["screening"])
def screen(
    request: ScreenRequest,
    limit: int = Query(DEFAULT_MATCH_LIMIT, ge=1, le=500),
) -> list[EvidenceRecord]:
    """Screen an arbitrary KYC entity against the sanctions index.

    Returns the top `limit` CONFIRMED_MATCH and POSSIBLE_MATCH evidence records,
    highest score first. An empty list means no candidate cleared the 0.55
    threshold.
    """
    return get_registry().screen(request.model_dump(), limit=limit)


@app.get("/customers", response_model=CustomerPage, tags=["screening"])
def list_customers(
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    """Page through the client book — use this to find IDs to screen."""
    registry = get_registry()
    page = registry.clients[offset : offset + limit]
    return {
        "total": len(registry.clients),
        "limit": limit,
        "offset": offset,
        "customers": [
            {
                "entity_id": c["entity_id"],
                "name": c["name"],
                "country": c["country"],
                "sector": c["sector"],
                "pep_flag": c["pep_flag"],
                "sanctions_flag": c["sanctions_flag"],
            }
            for c in page
        ],
    }


@app.get(
    "/customers/{customer_id}/sanctions-matches",
    response_model=list[EvidenceRecord],
    tags=["screening"],
)
def sanctions_matches(
    customer_id: str = PathParam(..., examples=["CLIENT-1", "1"]),
    limit: int = Query(DEFAULT_MATCH_LIMIT, ge=1, le=500),
) -> list[EvidenceRecord]:
    """Playbook §7 contract for Part 3 (Risk Intelligence)."""
    try:
        return get_registry().get_sanctions_matches(customer_id, limit=limit)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown customer: {customer_id}")


# -- adverse media ----------------------------------------------------------

@app.post("/adverse-media/analyze", response_model=AdverseMediaFinding, tags=["adverse-media"])
def analyze_adverse_media(request: AdverseMediaRequest) -> AdverseMediaFinding:
    """Analyze an article as untrusted data and flag prompt-injection attempts.

    Claim extraction is a keyword heuristic over verbatim source sentences —
    the playbook's LLM extraction and guard passes are not implemented. The
    response `metadata` says so explicitly.
    """
    registry = get_registry()

    article = request.article
    source_url = request.source_url
    if article is None:
        if not request.article_name:
            raise HTTPException(
                status_code=422, detail="Provide either 'article' or 'article_name'"
            )
        article = registry.articles.get(request.article_name)
        if article is None:
            raise HTTPException(
                status_code=404,
                detail=f"Unknown article. Available: {sorted(registry.articles)}",
            )
        source_url = f"file://data/articles/{request.article_name}"

    return registry.analyze_article(request.entity_id, article, source_url)


@app.get("/adverse-media/articles", response_model=dict[str, list[str]], tags=["adverse-media"])
def list_articles() -> dict[str, list[str]]:
    """Bundled demo articles you can pass as `article_name`."""
    return {"articles": sorted(get_registry().articles)}


@app.get(
    "/customers/{customer_id}/adverse-media",
    response_model=list[AdverseMediaFinding],
    tags=["adverse-media"],
)
def customer_adverse_media(customer_id: str) -> list[AdverseMediaFinding]:
    """Playbook §7 contract for Part 3.

    Returns findings already analyzed for this entity. Empty until you POST to
    /adverse-media/analyze with a matching entity_id — findings are held in
    process memory, not persisted.
    """
    return get_registry().get_adverse_media(customer_id)


# -- audit ------------------------------------------------------------------

@app.get("/audit/events", response_model=AuditEventPage, tags=["audit"])
def audit_events(limit: int = Query(50, ge=1, le=1000)) -> dict[str, Any]:
    """Playbook §7/§10 events emitted by Part 2, newest last.

    Part 2 emits; Part 1 owns the durable hash-chained log. Until Part 1's sink
    is registered via `set_audit_sink()`, these are held in a bounded in-process
    sink — `dropped` reports anything aged out so a partial view is never
    mistaken for the full history.
    """
    sink = get_audit_sink()
    events = sink.events(limit=limit) if isinstance(sink, InMemoryAuditSink) else []
    return {
        "total_emitted": sink.count if isinstance(sink, InMemoryAuditSink) else 0,
        "dropped": sink.dropped if isinstance(sink, InMemoryAuditSink) else 0,
        "returned": len(events),
        "sink": type(sink).__name__,
        "events": events,
    }


@app.get("/audit/verify", response_model=AuditVerifyResponse, tags=["audit"])
def audit_verify() -> dict[str, Any]:
    """Recompute the hash chain and report the first break, if any.

    Demo beat: mutate a stored event and this flips to valid=false, naming the
    entry where the chain breaks.
    """
    sink = get_audit_sink()
    if not isinstance(sink, InMemoryAuditSink):
        raise HTTPException(
            status_code=501,
            detail=f"{type(sink).__name__} does not expose chain verification",
        )
    return sink.verify_chain()


# -- UBO --------------------------------------------------------------------

@app.get("/ubo/structures", response_model=UboStructureList, tags=["ubo"])
def list_structures() -> dict[str, Any]:
    """Available ownership graphs and their node/edge counts."""
    registry = get_registry()
    return {
        "structures": [
            {
                "name": name,
                "nodes": graph.number_of_nodes(),
                "edges": graph.number_of_edges(),
                "roots": [n for n, deg in graph.in_degree() if deg == 0],
            }
            for name, graph in registry.graphs.items()
        ]
    }


@app.post("/ubo/trace", response_model=UboTraceResponse, tags=["ubo"])
def trace_ubo(request: UboTraceRequest) -> dict[str, Any]:
    """Walk an ownership chain and resolve every node against the sanctions list.

    Flags risk hidden behind ownership layers — a hit on any node in the chain,
    not just the top-level entity, is reported with its full ownership path.
    """
    try:
        return get_registry().trace_ubo(
            request.structure, request.root_entity_id, request.max_depth
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Not found: {exc.args[0]}")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
