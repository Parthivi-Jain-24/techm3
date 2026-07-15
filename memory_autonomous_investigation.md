# Continuous KYC — Project Memory

## What Was Built

Part 4 scaffold: **Autonomous Investigation** module for a Continuous KYC system.

- **FastAPI backend** (`/backend`) with a modular package layout under `/backend/app`.
- **Vite + React frontend** (`/frontend`) with a minimal investigation dashboard that calls the backend API.
- **Data loader modules** (`/backend/app/data_loaders/`) — five specialized loaders that read CSVs and JSON from `/data`, cache in memory on first access, and expose clean query functions plus real-time live news RSS screening.
- **Pipeline schemas** (`/backend/app/schemas/`) — Pydantic v2 models for every stage of the investigation pipeline: screening → investigation → debate → SAR.
- **Investigation agent** (`/backend/app/agents/investigation_agent.py`) — LLM-powered agent that gathers client data via loaders (plus live adverse news), calls NVIDIA API (`z-ai/glm-5.2` / `mistralai/mistral-nemotron` via `openai` Python SDK), and returns a validated `InvestigationFinding`.
- **Debate agent** (`/backend/app/agents/debate_agent.py`) — Adversarial cross-check: prosecutor, defender, and judge LLM calls that evaluate an `InvestigationFinding` and produce a `DebateVerdict`.
- **Grounding guardrail** (`/backend/app/agents/grounding_guardrail.py`) — Post-LLM validation that verifies every evidence citation resolves to real data. Strips unverifiable claims and collects them in a separate list.
- **Privacy guardrail** (`/backend/app/agents/privacy_guardrail.py`) — Rule-based PII redaction pass on `SARDraft` before human review. Redacts DOB, SSN, passport numbers, email, phone, and account numbers. Tags each redaction with GDPR article justification and OPP-115 category.
- **SAR drafting agent** (`/backend/app/agents/sar_agent.py`) — Stage 4 LLM agent that takes a verified `InvestigationFinding` + `DebateVerdict` (escalate_to_sar), calls the LLM to produce a `SARDraft`, then runs both guardrails (grounding + privacy) before returning.
- **Pipeline orchestrator** (`/backend/app/services/orchestrator.py`) — Runs the full pipeline (investigate → verify → debate → verify × 2 → SAR) for a given `client_id` and returns a single `PipelineResult` with every intermediate output, guardrail report, and per-stage timing.
- **API routes** (`/backend/app/routers/investigation.py`) — Three endpoints: `GET /clients` (dropdown data), `POST /investigate/{client_id}` (full pipeline), `GET /investigate/{client_id}/status` (cached result / running state). In-memory results cache for status polling.

## Folder Structure

```
TMCode2/
├── data/
│   ├── kyc_profiles/
│   │   ├── clients_with_fatf_ofac.csv     (2000 clients)
│   │   └── client_account_mapping.csv     (122 account→client mappings)
│   ├── aml_transactions/
│   │   └── SAML-D.csv                     (11057 transactions)
│   ├── sanctions/
│   │   ├── ofac_sdn.csv                   (19156 entries, no header)
│   │   └── opensanctions_targets.csv      (1.3M entries)
│   └── gdpr_text/
│       └── gdpr.json                      (661 paragraphs across 99 articles)
├── backend/
│   ├── requirements.txt
│   ├── .env.example
│   └── app/
│       ├── main.py                        # FastAPI app with CORS for localhost:5173
│       ├── config.py                      # Settings via pydantic-settings (env vars)
│       ├── agents/
│       │   ├── investigation_agent.py     # LLM investigation agent (NVIDIA API / GLM-5.2 & Mistral Nemotron)
│       │   ├── debate_agent.py            # Adversarial cross-check: prosecutor, defender, judge
│       │   ├── sar_agent.py               # SAR drafting agent — LLM + grounding + privacy guardrails
│       │   ├── grounding_guardrail.py     # Evidence citation verifier — strips ungrounded claims
│       │   └── privacy_guardrail.py       # PII redaction pass on SARDraft before human review
│       ├── routers/
│       │   └── investigation.py           # API routes: GET /clients, POST/GET /investigate/{id}
│       ├── services/
│       │   ├── orchestrator.py            # Full-pipeline orchestrator: investigate -> debate -> SAR
│       │   └── investigation_service.py   # Legacy stub (alert-based, pre-orchestrator)
│       ├── schemas/
│       │   ├── __init__.py                # Re-exports all models
│       │   ├── common.py                  # RiskLevel, ConfidenceLevel, SourceType, EvidenceItem
│       │   ├── signals.py                 # Stage 1: EntitySignal, TransactionSignal
│       │   ├── findings.py                # Stage 2: InvestigationFinding, RiskIndicator
│       │   ├── debate.py                  # Stage 3: DebateArgument, DebateVerdict
│       │   ├── sar.py                     # Stage 4: SARDraft
│       │   └── investigation.py           # API layer: Alert, Finding, InvestigationResult
│       └── data_loaders/
│           ├── __init__.py                # Re-exports all public functions
│           ├── kyc_loader.py              # Client profiles
│           ├── transaction_loader.py      # Transactions via account mapping join
│           ├── sanctions_loader.py        # OFAC SDN + OpenSanctions fuzzy search
│           ├── gdpr_loader.py             # GDPR article keyword search
│           └── adverse_media_loader.py    # Live Google News RSS screening (sub-second, free)
└── frontend/
    ├── package.json
    ├── vite.config.js                     # Dev proxy /api → localhost:8000
    ├── index.html
    └── src/
        ├── main.jsx
        ├── App.jsx                        # Full dashboard: client selector, pipeline trigger, results view
        └── App.css                        # Card layout, verdict badges, timing bar, evidence tables
```

## Pipeline Schema Definitions

### Shared Types (common.py)

```
RiskLevel(Enum)        — low | medium | high | critical
ConfidenceLevel(Enum)  — low | medium | high
SourceType(Enum)       — kyc_profile | transaction | sanctions_list | gdpr | pep_registry | open_source | llm_analysis
EvidenceItem(BaseModel) — { claim: str, source_type: SourceType, source_id: str, confidence: ConfidenceLevel }
```

### Stage 1 → Screening Signals (signals.py)

Produced by data loaders + fuzzy matching. Raw signals before LLM analysis.

```
EntitySignal {
    client_id: int
    matched_entity: str           # Name as it appears on the sanctions/PEP list
    confidence: ConfidenceLevel
    matched_list: str             # e.g. "OFAC_SDN", "OpenSanctions"
    disambiguation_reason: str    # Why this match is/isn't the same person
}

TransactionSignal {
    client_id: int
    transaction_id: str           # Composite key: Date|Time|Sender|Receiver
    laundering_type: str          # From SAML-D: "Smurfing", "Fan_Out", "Normal_Group", etc.
    is_laundering: bool
    amount: float
    date: str                     # YYYY-MM-DD
}
```

**Feeds →** InvestigationFinding (Stage 2). The investigator agent receives these raw signals as context.

### Stage 2 → Investigation Findings (findings.py)

Produced by the LLM investigator agent. Synthesizes signals into a coherent finding.

```
RiskIndicator {
    indicator: str                # Short label, e.g. "FATF high-risk jurisdiction"
    severity: RiskLevel
    detail: str
}

InvestigationFinding {
    client_id: int
    summary: str                  # Plain-English synopsis
    risk_indicators: [RiskIndicator]
    evidence: [EvidenceItem]      # Claims with provenance
    confidence: ConfidenceLevel
}
```

**Feeds →** DebateArgument (Stage 3). The prosecutor and defender agents each receive the full InvestigationFinding to argue for/against escalation.

### Stage 3 → Adversarial Debate (debate.py)

Prosecutor argues for escalation; defender argues against. A judge agent issues the verdict.

```
DebatePosition(Enum)   — risk_confirmed | false_positive

DebateArgument {
    position: DebatePosition
    argument: str                 # The substantive claim
    cited_evidence: [str]         # References to EvidenceItem.source_id values
    strength: ConfidenceLevel
}

Verdict(Enum)          — escalate_to_sar | further_investigation | false_positive_clear

DebateVerdict {
    verdict: Verdict
    reasoning: str                # Step-by-step explanation
    confidence: ConfidenceLevel
    key_deciding_evidence: [str]  # source_id references that most influenced the ruling
}
```

**Feeds →** SARDraft (Stage 4) if verdict is `escalate_to_sar`. If `false_positive_clear` the case is closed. If `further_investigation` the pipeline schedules re-investigation.

### Stage 4 → SAR Draft (sar.py)

Generated only when the debate verdict is `escalate`. Draft for compliance officer review.

```
SARDraft {
    client_id: int
    subject_information: str      # Structured summary: name, type, jurisdiction, accounts
    narrative: str                # Free-text SAR narrative
    red_flags: [str]              # Bullet-point red flags
    regulatory_basis: [str]       # Applicable regulations, e.g. "GDPR Article 6"
    evidence_appendix: [EvidenceItem]
    recommended_action: str       # "file SAR", "enhanced monitoring", "account freeze"
    disclaimer: str               # Default: AI-generated, requires human review
}
```

**Feeds →** Human compliance officer for review and filing.

### API Layer (investigation.py)

Existing REST API models that wrap the pipeline for external callers.

```
Alert              — { alert_id, customer_id, alert_type, description, risk_level }
InvestigationRequest — { alert: Alert }
Finding            — { source, detail, risk_contribution: RiskLevel }
InvestigationResult — { alert_id, customer_id, summary, findings[], recommended_action, overall_risk }
```

## Pipeline Data Flow

```
┌──────────────────────────────────────────────────────┐
│  Orchestrator: run_pipeline(client_id)               │
│  POST /api/v1/investigate/{client_id}                │
│                                                      │
│  ┌──────────────────────────────────────────────┐    │
│  │  Stage 2: Investigation Agent                │    │
│  │  investigate(client_id)                      │    │
│  │  → InvestigationFinding                      │    │
│  └───────────────┬──────────────────────────────┘    │
│                  │                                    │
│                  ▼                                    │
│  ┌──────────────────────────────────────────────┐    │
│  │  ✓ Grounding: verify_finding()               │    │
│  │  Strip unverifiable evidence citations.      │    │
│  │  → InvestigationStage { finding, guardrail } │    │
│  └───────────────┬──────────────────────────────┘    │
│                  │                                    │
│                  ▼                                    │
│  ┌──────────────────────────────────────────────┐    │
│  │  Stage 3: Debate Agent                       │    │
│  │  run_debate(finding)                         │    │
│  │  Prosecutor + Defender (parallel) → Judge    │    │
│  └───────────────┬──────────────────────────────┘    │
│                  │                                    │
│                  ▼                                    │
│  ┌──────────────────────────────────────────────┐    │
│  │  ✓ Grounding: verify_debate_argument() x 2  │    │
│  │  Strip cited_evidence refs for both sides.   │    │
│  │  → DebateStage { pros, def, verdict,         │    │
│  │                   pros_guardrail, def_guard } │    │
│  └───────────────┬──────────────────────────────┘    │
│                  │                                    │
│          ┌───────┼───────────┐                        │
│          │ escalate_to_sar   │ other verdicts         │
│          ▼                   ▼                        │
│  ┌────────────────┐   Pipeline ends                  │
│  │  Stage 4: SAR  │   (outcome = verdict)            │
│  │  draft_sar()   │                                  │
│  │  → LLM call    │                                  │
│  │  → verify_sar  │                                  │
│  │  → redact_sar  │                                  │
│  │  → SARStage    │                                  │
│  └───────┬────────┘                                  │
│          │                                            │
│          ▼                                            │
│  PipelineResult                                      │
│  { outcome, investigation, debate, sar?,             │
│    total_duration_ms }                               │
└──────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────┐
│  Human review    │
└─────────────────┘
```

## Data Loader Function Signatures

All importable from `app.data_loaders`:

### kyc_loader.py

| Function | Signature | Returns |
|---|---|---|
| `get_client_profile` | `(client_id: int) -> dict \| None` | Full profile dict with typed fields (int flags, float opacity score) |
| `list_all_client_ids` | `() -> list[int]` | All 2000 client IDs |

Source columns: `client_id, client_name, client_type, sector, sector_risk, country, pep_flag, sanctions_flag, fatf_country_flag, ofac_country_flag, sectoral_sanctions_flag, ownership_opacity_score`

### transaction_loader.py

| Function | Signature | Returns |
|---|---|---|
| `get_accounts_for_client` | `(client_id: int) -> set[str]` | Account numbers from mapping table |
| `get_client_transactions` | `(client_id: int) -> list[dict]` | Deduplicated transactions where client is sender OR receiver |

Join logic: `client_account_mapping.csv` maps `client_id → account`, then `SAML-D.csv` is indexed by both `Sender_account` and `Receiver_account`. Results are deduplicated by `(Date, Time, Sender_account, Receiver_account, Amount)`.

Source columns (SAML-D): `Time, Date, Sender_account, Receiver_account, Amount, Payment_currency, Received_currency, Sender_bank_location, Receiver_bank_location, Payment_type, Is_laundering, Laundering_type`

### sanctions_loader.py

| Function | Signature | Returns |
|---|---|---|
| `get_sanctions_matches` | `(name: str, *, threshold: int=40, limit: int=10) -> list[dict]` | Hits with `{source, name, aliases, country, info, score}` |

Scoring: 100=exact, 80=substring, 60×(token overlap ratio). Searches both OFAC SDN and OpenSanctions name+aliases fields.

OFAC SDN assumed columns (no header): `ent_num, SDN_Name, SDN_Type, Program, Title, Call_Sign, Vess_type, Tonnage, GRT, Vess_flag, Vess_owner, Remarks`

### gdpr_loader.py

| Function | Signature | Returns |
|---|---|---|
| `get_gdpr_article` | `(query: str, *, limit: int=5) -> list[dict]` | Paragraphs with `{article_id, article_title, article_text, article_recitals, score}` |
| `get_gdpr_article_by_id` | `(article_id: str) -> list[dict]` | All paragraphs for that article ID |

Note: GDPR data has 661 entries across 99 unique `article_id` values — each entry is a paragraph/sub-section. Search deduplicates by exact `article_text`.

### adverse_media_loader.py

| Function | Signature | Returns |
|---|---|---|
| `get_adverse_media` | `(client_name: str, *, max_articles: int=4) -> list[dict]` | Live news articles with `{source_id, title, url, published, source}` |

Note: Queries Google News RSS (`https://news.google.com/rss/search?q=...`) in real-time. Sub-second latency, 100% free forever, no API key needed. Fallbacks to general AML/sanctions news alerts if exact corporate name has zero news hits.

## Key Decisions

| Decision | Rationale |
|---|---|
| **pydantic-settings** for config | Reads `.env` automatically; type-safe settings with defaults |
| **NVIDIA API (`integrate.api.nvidia.com`)** | High-performance enterprise LLMs accessed via standard `openai` Python SDK |
| **Vite dev proxy** (`/api → :8000`) | Avoids CORS issues in dev without extra config; CORS middleware is also present as a fallback |
| **Pydantic v2** schemas | `RiskLevel` enum, typed `Finding` & `InvestigationResult` for strict request/response validation |
| **Data loaded from `/data` folder** | Keeps sample data separate from app code; path configurable via `DATA_FOLDER` env var |
| **Lazy-load + module-global cache** | CSVs/JSON read once on first function call, kept in module-level dicts. No per-request disk I/O |
| **Transaction join via account mapping** | `client_id` doesn't appear in SAML-D; the mapping CSV bridges clients to account numbers |
| **Token-overlap scoring for sanctions/GDPR** | Lightweight fuzzy match — not production-grade, but gives the LLM agent ranked candidates to reason over |
| **OFAC SDN column names assigned manually** | File has no header row; columns follow the standard OFAC SDN CSV format |
| **GDPR dedup by article_text** | Source data has duplicate-looking entries per article; dedup prevents identical text from cluttering results |
| **Single RiskLevel in common.py** | `investigation.py` imports from `common.py` instead of redefining — one source of truth |
| **Schemas split by pipeline stage** | Each file maps to one pipeline step; keeps imports focused and makes the data-flow explicit |
| **EvidenceItem as shared building block** | Used in InvestigationFinding.evidence, DebateArgument.cited_evidence (by source_id ref), and SARDraft.evidence_appendix — single chain of provenance |
| **DebateVerdict.verdict as 3-way enum** | `escalate_to_sar` triggers SAR generation; `false_positive_clear` closes the case; `further_investigation` schedules re-investigation — covers all real outcomes |
| **GLM-5.2 & Mistral Nemotron via NVIDIA API** | Enterprise-grade reasoning models (`z-ai/glm-5.2` and `mistralai/mistral-nemotron`) ideal for high-volume compliance screening and complex adversarial debate |
| **Structured output via `response_format.json_schema`** | Enforces InvestigationFinding schema server-side with `strict: true`; schema also included in prompt as a hint for models that ignore the API-level constraint |
| **Prosecutor + Defender run in parallel** | Both only need the InvestigationFinding — no data dependency between them, so `asyncio.gather` cuts wall-clock time nearly in half |
| **Position/verdict forced after LLM parse** | `raw["position"] = "risk_confirmed"` / `"false_positive"` ensures the model can't accidentally swap roles, same pattern as investigation agent forcing `client_id` |
| **Three-agent adversarial design** | Single-agent analysis has confirmation bias. Forcing one agent to argue FOR risk and another AGAINST surfaces weaknesses in the evidence. The judge evaluates only on evidence quality, not rhetoric. |
| **Grounding guardrail strips, doesn't reject** | Stripping unverifiable claims preserves the rest of the analysis. Logging the stripped items lets compliance officers see what the LLM tried to cite but couldn't substantiate. |
| **Fuzzy source_id parsing** | LLMs produce free-form `source_id` strings — the guardrail tolerates prefixes (`txn:`, `ofac_sdn:`), composite keys (`Date\|Time\|Sender\|Receiver`), and partial matches rather than demanding exact format. |
| **Sanctions substring min length = 4** | Prevents ultra-short sanctions names (e.g. "Al") from matching any source_id via substring. Requires at least 4 characters for substring matching. |
| **Debate citations verified against finding** | `verify_debate_argument` cross-references cited_evidence against the finding's surviving (already-verified) source_ids, creating a transitive trust chain. |
| **No-check source types pass through** | `pep_registry`, `open_source`, `llm_analysis` have no ground-truth dataset to verify against, so they're passed through and counted separately as `skipped`. |
| **SAR agent runs both guardrails inline** | `draft_sar()` calls `verify_sar()` then `redact_sar()` internally. Caller gets a `SARResult` that is guaranteed evidence-verified and PII-redacted — can't accidentally skip a guardrail step. |
| **SAR prompt receives finding + verdict** | The LLM sees the full evidence chain (from InvestigationFinding) and the judge's reasoning (from DebateVerdict). This lets it write a narrative addressing the specific factors the judge found decisive. |
| **Orchestrator returns all intermediates** | `PipelineResult` carries every stage's output, guardrail reports, and per-stage timing. The frontend can render the full reasoning trail without needing separate API calls per stage. |
| **Conditional SAR stage** | SAR drafting only runs when verdict is `escalate_to_sar`. For `further_investigation` or `false_positive_clear`, the pipeline returns the debate stage output and stops — no wasted LLM call. |
| **Per-stage timing** | Each stage wrapper includes `duration_ms`. Lets the frontend show a timing breakdown and helps identify slow LLM calls in production. |
| **Orchestrator is client_id-in, PipelineResult-out** | Single function signature: `run_pipeline(client_id) -> PipelineResult`. The router just passes the path param; all data gathering and sequencing is internal. |
| **New route: POST /api/v1/investigate/{client_id}** | Separate from the legacy alert-based endpoint. Takes just a client_id, runs the full pipeline, returns the combined result. |
| **GET /clients returns flag booleans** | `ClientSummary` includes `pep_flag`, `sanctions_flag`, `fatf_country_flag` as booleans (coerced from 0/1 ints). Lets the frontend show risk badges without a full profile lookup. |
| **In-memory results cache** | `_results_cache` stores completed `PipelineResult` by client_id. Simple dict — sufficient for single-process dev server. GET `/status` reads from it. |
| **409 on duplicate concurrent runs** | `_running` set tracks in-flight pipelines. Prevents accidental double-runs of the same client (each run costs multiple LLM calls). |
| **404 on unknown client_id** | POST `/investigate/{client_id}` checks `get_client_profile` before starting the pipeline. Fails fast with 404 rather than running a pipeline that will produce a useless low-confidence finding. |
| **Legacy endpoint marked deprecated** | `POST /investigate` (alert-based) kept for backward compat but marked `deprecated=True` in OpenAPI metadata. |

## Assumptions About File Formats

1. **clients_with_fatf_ofac.csv** — has header row; `client_id` is a unique integer; flags are 0/1 integers; `ownership_opacity_score` is a float.
2. **client_account_mapping.csv** — has header row; one client can map to multiple accounts; `account` is a string (numeric but treated as text).
3. **SAML-D.csv** — has header row; `Amount` is a float; `Is_laundering` is 0/1; accounts are referenced by `Sender_account` and `Receiver_account` string columns.
4. **ofac_sdn.csv** — NO header row; 12 positional columns following standard OFAC SDN format; `-0-` is the null sentinel.
5. **opensanctions_targets.csv** — has header row with quoted fields; key columns: `name`, `aliases`, `countries`, `sanctions`.
6. **gdpr.json** — JSON array of objects with keys `article_id`, `article_title`, `article_text`, `article_recitals`; multiple entries per article (paragraphs).

## Next Steps

1. **Add streaming** (SSE or WebSocket) so the frontend can show investigation progress in real time rather than waiting for the full pipeline to complete.
2. **Part 5 dashboard** — more advanced visualizations, historical investigation view, compliance officer workflow.

## Frontend Dashboard (frontend/src/)

### What It Does

Single-page React dashboard that lets a compliance officer select a client, run the full investigation pipeline, and view every stage's output in structured panels.

### Files

| File | Purpose |
|------|---------|
| `App.jsx` | Main component — state management, API calls, all sub-panels rendered inline |
| `App.css` | Card-based layout, verdict badges, timing bar, evidence tables, responsive grid |
| `main.jsx` | React entry point (unchanged) |

### How It Maps to Backend Endpoints

| UI Action | Endpoint Called | When |
|-----------|----------------|------|
| Page load | `GET /api/v1/clients` | On mount — populates the client dropdown with all 2000 clients |
| "Investigate" click | `POST /api/v1/investigate/{client_id}` | Runs full pipeline; shows spinner for 15-60s; renders `PipelineResult` on success |
| Error handling | — | 409 → "already running" message; 404 → "not found"; 502 → server error |

### Results View Panels (rendered from PipelineResult)

| Panel | Data Source | Shows |
|-------|-------------|-------|
| **Outcome Banner** | `result.outcome` | Color-coded verdict badge (red/amber/green) + client ID |
| **Timing Bar** | `*.duration_ms` | Stacked horizontal bar showing investigation / debate / SAR stage durations |
| **Investigation Finding** | `result.investigation` | Summary, risk indicators with severity badges, evidence table, grounding guardrail stats |
| **Adversarial Debate** | `result.debate` | Prosecutor and defender arguments side-by-side, cited evidence, guardrail stats per side, judge verdict with reasoning |
| **SAR Draft** | `result.sar` (conditional) | Subject info, narrative, red flags, regulatory basis, recommended action, evidence appendix, disclaimer |
| **Redaction Log** | `result.sar.privacy_guardrail` | Table of every PII redaction: field, original text, replacement, GDPR article, OPP-115 category |

### Client Dropdown Format

Each option shows: `#ID — Name (Country, Risk Level) [Flags]`

Flags shown as tags: `PEP`, `SANC` (sanctions), `FATF` — only when the corresponding boolean flag is true.

### Design Decisions

| Decision | Rationale |
|----------|-----------|
| **Single-file component** | Dashboard is one page with no routing — splitting into files adds complexity without benefit at this stage. Part 5 can refactor into components. |
| **No additional dependencies** | React 18 + native fetch + CSS is sufficient. No state library, no component library — keeps the bundle minimal. |
| **Inline guardrail stats** | Each panel shows its own grounding guardrail stats (verified/stripped/skipped) so the compliance officer sees evidence quality alongside findings. |
| **Debate side-by-side layout** | Prosecutor (red border) and defender (green border) render in a CSS grid that collapses to single-column on mobile. |
| **Conditional SAR panel** | Only renders when `result.sar` is non-null (i.e., verdict was `escalate_to_sar`). |
| **Expandable unverified citations** | Stripped citations hidden behind a `<details>` toggle to avoid cluttering the view — compliance officers can expand when needed. |
## Investigation Agent (agents/investigation_agent.py)

### Role

Stage 2 of the pipeline. Takes a `client_id`, gathers all available data via the data loaders, sends it to the LLM, and returns a validated `InvestigationFinding`.

### Function Signature

```python
async def investigate(client_id: int) -> InvestigationFinding
```

If the client profile doesn't exist, returns a low-confidence finding with "No KYC profile found" rather than raising.

### Data Loader Integration

The agent calls three data loaders internally — callers only pass `client_id`:

| Loader call | What it provides | How it's used in the prompt |
|---|---|---|
| `get_client_profile(client_id)` | Full KYC profile dict | Shown as `## Client Profile` JSON block |
| `get_client_transactions(client_id)` | Joined transactions via account mapping | Shown as `## Transactions` — capped at 50 in the prompt to stay within context limits |
| `get_sanctions_matches(client_name)` | OFAC SDN + OpenSanctions fuzzy hits | Shown as `## Sanctions Screening Matches` |

### LLM Call Details

| Setting | Value |
|---|---|
| **Provider** | NVIDIA API (`https://integrate.api.nvidia.com/v1`) via `openai` Python SDK |
| **Model** | `z-ai/glm-5.2` or `mistralai/mistral-nemotron` (configurable via `MODEL_NAME` env var) |
| **Temperature** | 0.2 (low, for deterministic compliance output) |
| **Structured output** | `response_format.json_schema` with the `InvestigationFinding` Pydantic JSON schema, `strict: true` |
| **Timeout** | 120 seconds |

### Prompt Design Decisions

| Decision | Rationale |
|---|---|
| **System prompt mandates source citation** | Every claim must reference a `source_id` (transaction_id, sanctions record, profile field). Prevents hallucinated evidence — critical for compliance. |
| **Facts vs inferences distinction** | System prompt rule 3 requires the LLM to label inferences. Downstream debate agents need to know which claims are grounded vs. reasoned. |
| **Sanctions disambiguation instruction** | Rule 4 tells the LLM to evaluate name matches using DOB/nationality/aliases. Reduces false-positive escalations from common-name collisions. |
| **Pattern analysis over transactions** | Rule 5 asks for cross-transaction pattern detection (structuring, timing clusters) rather than per-transaction flags. More useful than repeating individual alerts. |
| **JSON-only output rule** | Rule 6 + `response_format.json_schema` forces structured output. The Pydantic schema is included in the prompt as a hint AND enforced server-side via `strict: true`. |
| **Transaction cap at 50** | Prevents prompt from exceeding context window for high-volume clients. 50 transactions is enough to detect patterns; the prompt notes the total count so the LLM knows data was truncated. |
| **`client_id` forced after parse** | `raw["client_id"] = client_id` ensures the finding always matches the requested client, even if the LLM echoes a different value. |
| **Low temperature (0.2)** | Compliance analysis should be deterministic and conservative, not creative. |

## Debate Agent (agents/debate_agent.py)

### Role

Stage 3 of the pipeline. Takes an `InvestigationFinding` from Stage 2 and runs an adversarial cross-check via three LLM calls:

1. **Prosecutor** — argues the client is a genuine compliance risk (`position="risk_confirmed"`)
2. **Defender** — argues the client is a false positive (`position="false_positive"`)
3. **Judge** — evaluates both arguments on evidence quality and issues a verdict

### Function Signature

```python
async def run_debate(finding: InvestigationFinding) -> DebateResult
```

`DebateResult` is a Pydantic model bundling all three outputs:

```python
class DebateResult(BaseModel):
    finding: InvestigationFinding   # the input, passed through for downstream use
    prosecution: DebateArgument
    defense: DebateArgument
    verdict: DebateVerdict
```

### Execution Flow

```
InvestigationFinding
         │
    ┌────┴────┐
    ▼         ▼           (parallel via asyncio.gather)
Prosecutor  Defender
    │         │
    └────┬────┘
         ▼
       Judge              (sequential — needs both arguments)
         │
         ▼
    DebateResult
```

### LLM Call Details

| Setting | Value |
|---|---|
| **Provider** | OpenRouter (same as investigation agent) |
| **Model** | `google/gemini-2.5-flash` (shared `settings.model_name`) |
| **Temperature** | 0.3 (slightly higher than investigator to allow varied argumentation) |
| **Structured output** | `response_format.json_schema` with `strict: true` — `DebateArgument` schema for prosecutor/defender, `DebateVerdict` schema for judge |
| **Timeout** | 120 seconds per call |
| **Parallelism** | Prosecutor and defender run concurrently; judge waits for both |

### Three-Agent Design Rationale

| Design choice | Why |
|---|---|
| **Adversarial structure** | A single agent assessing risk has confirmation bias — it tends to validate its own initial assessment. Forcing one agent to argue FOR and another AGAINST surfaces weaknesses in the evidence that a single analysis would gloss over. |
| **Evidence-only arguments** | Both prompts mandate `source_id` citations. This prevents rhetorical appeals and keeps the debate grounded in the actual data from Stage 2. |
| **Honest defender** | The defender prompt (rule 3) explicitly says "do not dismiss real red flags dishonestly." This prevents the defender from reflexively arguing everything is fine, which would make the debate meaningless. |
| **Judge evaluates evidence, not rhetoric** | Judge rule 1: "evaluate strictly on evidence cited, not rhetorical strength." This prevents the more eloquent agent from winning regardless of evidence quality. |
| **Position forced after parse** | `raw["position"] = "risk_confirmed"` / `"false_positive"` is set server-side after parsing. Even if the LLM outputs the wrong position value, the typing is guaranteed correct. Same pattern used in the investigation agent for `client_id`. |
| **Parallel prosecution/defense** | Both agents receive only the `InvestigationFinding` — no data dependency between them. Running them via `asyncio.gather` cuts wall-clock time nearly in half compared to sequential execution. |
| **3-way verdict** | `escalate_to_sar` (file a SAR), `further_investigation` (ambiguous, needs more data), `false_positive_clear` (close the case). The middle option acknowledges that not every case is clear-cut, reducing forced binary decisions on ambiguous evidence. |

## Grounding Guardrail (agents/grounding_guardrail.py)

### Role

Post-LLM validation layer that sits between every agent stage and the next. Verifies that evidence citations (`source_id` values) actually resolve to real records in the loaded datasets. Strips unverifiable claims and collects them in a structured report.

### Function Signatures

```python
def verify_finding(finding: InvestigationFinding) -> tuple[InvestigationFinding, GuardrailResult]
def verify_debate_argument(argument: DebateArgument, finding: InvestigationFinding) -> tuple[DebateArgument, GuardrailResult]
def verify_sar(sar: SARDraft) -> tuple[SARDraft, GuardrailResult]
```

Each returns a cleaned copy of the input (unverifiable evidence stripped) plus a `GuardrailResult`:

```python
class GuardrailResult(BaseModel):
    verified_count: int       # citations that resolved to real data
    stripped_count: int       # citations removed (hallucinated or unresolvable)
    skipped_count: int        # citations with no ground truth to check (llm_analysis, etc.)
    unverified: list[UnverifiedCitation]   # detail on each stripped citation

class UnverifiedCitation(BaseModel):
    claim: str
    source_id: str
    source_type: str
    reason: str               # why verification failed
```

### Where It's Called in the Pipeline

```
Investigation Agent  →  verify_finding()  →  Debate Agent
                                              ↓
                              verify_debate_argument() (× 2: prosecution + defense)
                                              ↓
                                          Judge Agent
                                              ↓
                              (if escalate_to_sar) SAR Agent  →  verify_sar()
                                              ↓
                                         Human review
```

### Verification Logic by Source Type

| source_type | Verified against | Method |
|---|---|---|
| `kyc_profile` | Client profile from `kyc_loader` | Checks if `source_id` contains any known profile field name (`sector_risk`, `pep_flag`, `sanctions_flag`, etc.) |
| `transaction` | SAML-D transaction index from `transaction_loader` | Extracts 6+ digit numbers and checks if any are known account numbers. Also tries parsing `Date\|Time\|Sender\|Receiver` composite keys. Falls back to checking the client's transactions for matching dates/amounts/accounts. |
| `sanctions_list` | OFAC SDN + OpenSanctions from `sanctions_loader` | Strips common prefixes (`ofac_sdn:`, `opensanctions:`), then checks for exact name match or substring match (min 4 chars to avoid false positives from short names like "Al"). |
| `gdpr` | GDPR articles from `gdpr_loader` | Extracts article number via regex (`article\s*\d+`), normalises to `article{N}`, and checks if `get_gdpr_article_by_id` returns results. |
| `pep_registry` | — | Passed through (no dataset loaded) |
| `open_source` | — | Passed through (no dataset loaded) |
| `llm_analysis` | — | Passed through (inference, not a data claim) |

### Debate Argument Verification

`verify_debate_argument` uses a different strategy: instead of checking raw data, it cross-references `cited_evidence` strings against the `source_id` values that survived `verify_finding()` on the InvestigationFinding. This creates a transitive trust chain — debate agents can only cite evidence that has already been verified against real data. Fuzzy matching (substring containment) handles minor formatting differences between the finding's `source_id` and the debate agent's citation.

## Privacy Guardrail (agents/privacy_guardrail.py)

### Role

Final pre-human-review pass that strips unnecessary PII from `SARDraft` free-text fields. Deterministic regex rules — no ML, no LLM call. Each redaction is tagged with:
- A **GDPR article** justifying the redaction (looked up from `gdpr.json` via `get_gdpr_article_by_id`)
- An **OPP-115 category** as a secondary heuristic (Data Retention, First Party Collection/Use, Third Party Sharing/Collection)

### Function Signature

```python
def redact_sar(sar: SARDraft) -> tuple[SARDraft, PrivacyGuardrailResult]
```

Returns a new `SARDraft` with PII redacted in free-text fields, plus a `PrivacyGuardrailResult` detailing every redaction:

```python
class RedactionAction(BaseModel):
    field: str                  # which SARDraft field was redacted
    original_snippet: str       # the text that was redacted (first 80 chars)
    replacement: str            # e.g. "[PASSPORT_REDACTED]"
    gdpr_article: str           # e.g. "GDPR article9 (Processing of special categories)"
    gdpr_justification: str     # article title from gdpr.json
    opp115_category: str        # OPP-115 sensitivity category
    description: str            # why this was redacted

class PrivacyGuardrailResult(BaseModel):
    redaction_count: int
    redactions: list[RedactionAction]
    gdpr_articles_cited: list[str]   # new GDPR refs added to regulatory_basis
```

### Redaction Rules (in order of application)

Rules are ordered most-specific-first to prevent partial matches from consuming tokens that belong to more specific patterns:

| # | Pattern | Replacement | GDPR Article | OPP-115 Category | Notes |
|---|---------|------------|--------------|-------------------|-------|
| 1 | Dates (YYYY-MM-DD, DD/MM/YYYY, Month DD YYYY) | `[DOB_REDACTED]` | Article 5 | Data Retention | **Context-aware**: only redacts when preceded by "born", "dob", "birth", "date of birth", or "d.o.b" within 40 chars. Transaction dates are preserved for SAR timeline. |
| 2 | SSN (XXX-XX-XXXX) | `[NATIONAL_ID_REDACTED]` | Article 9 | Data Retention | Runs before phone/account to avoid partial digit matches. |
| 3 | Passport (1-2 uppercase letters + 6-9 digits) | `[PASSPORT_REDACTED]` | Article 9 | Data Retention | Runs before account number rule — prevents digit portion from being caught by `\d{7,}`. |
| 4 | Email addresses | `[EMAIL_REDACTED]` | Article 5 | First Party Collection/Use | Standard email regex. |
| 5 | Phone numbers (+country code format) | `[PHONE_REDACTED]` | Article 5 | First Party Collection/Use | Requires `+` prefix (international format) — bare digit sequences fall to account rule. |
| 6 | Account numbers (7+ digits) | `[ACCT_REDACTED]` | Article 5 | Third Party Sharing/Collection | Negative lookbehind excludes `client_id=` prefix. Last rule — catches remaining long digit sequences. |

### Fields Processed

| Field | Treatment |
|---|---|
| `subject_information` | Full redaction pass |
| `narrative` | Full redaction pass |
| `red_flags` | Account numbers only (7+ digits masked) |
| `regulatory_basis` | GDPR article refs appended (not redacted) |
| `recommended_action` | Not redacted (legally required) |
| `disclaimer` | Not redacted |
| `evidence_appendix` | Not redacted (structured data, handled by grounding guardrail) |

### Where It's Called in the Pipeline

```
SAR Agent  →  verify_sar()  →  redact_sar()  →  Human review
```

The privacy guardrail runs **after** the grounding guardrail — evidence is verified first, then PII is stripped from the narrative fields.

### Design Decisions

| Decision | Rationale |
|---|---|
| **Rule ordering: specific → general** | Passport (`[A-Z]{1,2}\d{6,9}`) must run before account (`\d{7,}`) — otherwise the digit portion gets consumed by the wrong rule. SSN (`\d{3}-\d{2}-\d{4}`) before phone for the same reason. |
| **Single-pass with right-to-left replacement** | Each rule scans the current text (after prior rules), collects spans, then applies replacements right-to-left to preserve offset positions. Eliminates the stale-text bug from dual-loop approaches. |
| **DOB context guard** | Date patterns appear in both birth dates and transaction timelines. Only redacts when a birth-related keyword appears within 40 characters before the date — preserves the transaction timeline that compliance officers need. |
| **Phone requires + prefix** | Distinguishes international phone numbers from bare digit sequences (account numbers, IDs). If a phone number appears without `+` prefix, it falls through to the account number rule — still redacted, just with a different label. |
| **GDPR refs added to regulatory_basis** | Each redaction cites a GDPR article. These are deduplicated and appended to the SAR's `regulatory_basis` list so the compliance officer can see the legal justification for redactions alongside existing regulatory references. |
| **OPP-115 as secondary tag** | OPP-115 categories (Data Retention, First Party Collection/Use, Third Party Sharing/Collection) are attached for traceability but don't drive the redaction decision — GDPR articles are the primary authority. |
| **red_flags get minimal treatment** | Only account numbers are masked in bullet-point red flags. Other PII (names, dates) in red flags is typically necessary context for the compliance officer. |

## SAR Drafting Agent (agents/sar_agent.py)

### Role

Stage 4 of the pipeline. Takes a grounding-guardrail-verified `InvestigationFinding` and a `DebateVerdict` (with verdict `escalate_to_sar`), calls the LLM to produce a structured `SARDraft`, then runs both guardrails inline before returning a combined result.

### Function Signature

```python
async def draft_sar(
    finding: InvestigationFinding,
    verdict: DebateVerdict,
) -> SARResult
```

`SARResult` is a Pydantic model bundling the final SAR plus both guardrail reports:

```python
class SARResult(BaseModel):
    sar: SARDraft                        # final redacted SAR ready for human review
    grounding: GuardrailResult           # evidence citation verification report
    privacy: PrivacyGuardrailResult      # PII redaction report
```

### Execution Flow

```
InvestigationFinding + DebateVerdict
         |
         v
    LLM call (SARDraft)
         |
         v
    verify_sar()          -- grounding guardrail: strip unverifiable citations
         |
         v
    redact_sar()          -- privacy guardrail: redact PII, append GDPR refs
         |
         v
    SARResult
```

### LLM Call Details

| Setting | Value |
|---|---|
| **Provider** | OpenRouter (`https://openrouter.ai/api/v1/chat/completions`) |
| **Model** | `google/gemini-2.5-flash` (shared `settings.model_name`) |
| **Temperature** | 0.2 (low — compliance language should be deterministic and formal) |
| **Structured output** | `response_format.json_schema` with `SARDraft` schema, `strict: true` |
| **Timeout** | 120 seconds |

### User Prompt Structure

The user prompt provides two markdown-formatted JSON blocks:

| Section | Content |
|---|---|
| `## Investigation Finding` | Full `InvestigationFinding` JSON (including verified evidence with source_ids) |
| `## Debate Verdict` | Full `DebateVerdict` JSON (verdict, reasoning, key_deciding_evidence) |
| `## Required Output Schema` | `SARDraft` JSON schema as a hint |
| Instruction | "Draft the SARDraft JSON now. Every narrative claim must cite a source_id..." |

### Prompt Design Decisions

| Decision | Rationale |
|---|---|
| **System prompt mandates source citation** | Rule 2 requires every narrative claim to cite a `source_id`. Combined with the grounding guardrail running post-LLM, this creates two layers of citation enforcement. |
| **PII-avoidance instruction in prompt** | Rule 3 tells the LLM not to re-introduce raw PII. This is a first line of defense; the privacy guardrail catches anything that slips through. |
| **Generic AML basis when no GDPR** | Rule 4 prevents the LLM from inventing specific statute citations. If GDPR articles are provided (from the evidence), it cites them; otherwise it uses a generic "AML reporting obligation" reference. |
| **Formal compliance language** | Rule 5 enforces clear, factual language — no dramatisation, hedging proportional to confidence scores. Compliance officers read hundreds of these; clarity over style. |
| **Mandatory disclaimer** | Rule 6 + `SARDraft.disclaimer` default ensure every draft is clearly marked as AI-generated and requiring human sign-off. |
| **`client_id` forced after parse** | Same pattern as investigation and debate agents. `raw["client_id"] = finding.client_id` ensures the SAR always references the correct client regardless of what the LLM outputs. |
| **Both guardrails run inline** | `draft_sar()` calls `verify_sar()` then `redact_sar()` internally rather than leaving it to the caller. This guarantees every SAR returned from the agent is both evidence-verified and PII-redacted — the caller can't accidentally skip a guardrail. |
| **Low temperature (0.2)** | Matches the investigation agent. SAR narratives should be factual and reproducible, not creative. |
| **Finding + verdict as context** | The LLM sees both the evidence (from the finding) and the judge's reasoning (from the verdict). This lets it write a narrative that addresses the specific factors the judge found decisive. |

## Pipeline Orchestrator (services/orchestrator.py)

### Role

Entry point for the full investigation pipeline. Takes a `client_id`, runs every stage in sequence, and returns a single `PipelineResult` containing all intermediate outputs, guardrail reports, and per-stage timing. Exposed via `POST /api/v1/investigate/{client_id}`.

### Function Signature

```python
async def run_pipeline(client_id: int) -> PipelineResult
```

### Combined Response Shape (PipelineResult)

```python
class PipelineOutcome(str, Enum):
    ESCALATE_TO_SAR = "escalate_to_sar"
    FURTHER_INVESTIGATION = "further_investigation"
    FALSE_POSITIVE_CLEAR = "false_positive_clear"
    ERROR = "error"

class InvestigationStage(BaseModel):
    finding: InvestigationFinding        # verified finding (post-guardrail)
    guardrail: GuardrailResult           # evidence verification report
    duration_ms: int

class DebateStage(BaseModel):
    prosecution: DebateArgument          # verified prosecution argument
    prosecution_guardrail: GuardrailResult
    defense: DebateArgument              # verified defense argument
    defense_guardrail: GuardrailResult
    verdict: DebateVerdict               # judge's ruling
    duration_ms: int

class SARStage(BaseModel):
    sar: SARDraft                        # final redacted SAR
    grounding_guardrail: GuardrailResult # evidence verification
    privacy_guardrail: PrivacyGuardrailResult  # PII redaction log
    duration_ms: int

class PipelineResult(BaseModel):
    client_id: int
    outcome: PipelineOutcome
    investigation: InvestigationStage    # always present
    debate: DebateStage                  # always present
    sar: SARStage | None                 # only if escalate_to_sar
    total_duration_ms: int
    error: str | None                    # only if pipeline fails mid-run
```

### Execution Sequence

| Step | Function called | Output captured |
|---|---|---|
| 1 | `investigate(client_id)` | raw `InvestigationFinding` |
| 2 | `verify_finding(finding)` | verified finding + `GuardrailResult` → `InvestigationStage` |
| 3 | `run_debate(finding)` | `DebateResult` (prosecution + defense + verdict) |
| 4a | `verify_debate_argument(prosecution, finding)` | verified prosecution + `GuardrailResult` |
| 4b | `verify_debate_argument(defense, finding)` | verified defense + `GuardrailResult` → `DebateStage` |
| 5 | `draft_sar(finding, verdict)` *(conditional)* | `SARResult` (internally runs verify_sar + redact_sar) → `SARStage` |

Step 5 only executes when the debate verdict is `escalate_to_sar`. For `further_investigation` or `false_positive_clear`, the pipeline stops after step 4 and returns the debate output.

### API Endpoint

```
POST /api/v1/investigate/{client_id}  →  PipelineResult (JSON)
```

No request body needed — the `client_id` path parameter drives everything. The response contains the full reasoning trail: investigation finding, debate transcript with both sides + verdict, SAR draft (if applicable), all guardrail reports, and per-stage timing.

### What the Frontend Gets

The `PipelineResult` is designed so a dashboard can render each stage as a panel:

| Panel | Data source | What to show |
|---|---|---|
| **Investigation** | `investigation.finding` | Summary, risk indicators, evidence list |
| **Evidence Audit** | `investigation.guardrail` | Verified vs. stripped citations |
| **Debate** | `debate.prosecution`, `debate.defense` | Side-by-side arguments with cited evidence |
| **Verdict** | `debate.verdict` | Verdict badge, reasoning, key evidence, confidence |
| **SAR Draft** | `sar.sar` | Subject info, narrative, red flags, recommended action |
| **Redaction Log** | `sar.privacy_guardrail` | What PII was redacted and why (GDPR refs) |
| **Timing** | `*_stage.duration_ms`, `total_duration_ms` | Per-stage breakdown bar |

## API Contract (routers/investigation.py)

All endpoints are prefixed with `/api/v1`. The backend runs on port 8000; the React frontend on 5173 proxies `/api` via vite.config.js.

### GET /api/v1/clients

Returns every client in the KYC dataset for a frontend dropdown.

**Request:** none (no params, no body)

**Response:** `ClientListResponse`

```json
{
  "total": 2000,
  "clients": [
    {
      "client_id": 1,
      "client_name": "Wells-Turner",
      "country": "JP",
      "sector": "Finance",
      "sector_risk": "High",
      "pep_flag": false,
      "sanctions_flag": false,
      "fatf_country_flag": false
    }
  ]
}
```

`ClientSummary` fields:

| Field | Type | Description |
|---|---|---|
| `client_id` | int | Unique identifier |
| `client_name` | str | Company / entity name |
| `country` | str | ISO 2-letter country code |
| `sector` | str | Business sector |
| `sector_risk` | str | Risk rating (Low / Medium / High) |
| `pep_flag` | bool | Politically Exposed Person flag |
| `sanctions_flag` | bool | On a sanctions list |
| `fatf_country_flag` | bool | In a FATF high-risk jurisdiction |

### POST /api/v1/investigate/{client_id}

Runs the full pipeline synchronously and returns the combined result. Caches the result for the status endpoint.

**Request:** path param `client_id: int` (no body)

**Response:** `PipelineResult` (see Orchestrator section for full schema)

**Error responses:**

| Status | When |
|---|---|
| 404 | `client_id` not found in KYC dataset |
| 409 | Pipeline already running for this `client_id` |
| 502 | Pipeline failed mid-run (LLM error, network, etc.) |

**Timing:** expect 15-60 seconds depending on LLM response times (4 sequential LLM calls: investigation + prosecutor + defender in parallel + judge + optional SAR).

### GET /api/v1/investigate/{client_id}/status

Returns the cached result if the client has been investigated, or a status indicator.

**Request:** path param `client_id: int`

**Response:** `PipelineStatusResponse`

```json
{
  "client_id": 42,
  "status": "completed",
  "result": { ... PipelineResult ... },
  "error": null
}
```

| `status` value | Meaning | `result` | `error` |
|---|---|---|---|
| `not_started` | No pipeline has been run | null | null |
| `running` | Pipeline is currently in progress | null | null |
| `completed` | Finished successfully | full `PipelineResult` | null |
| `error` | Last run failed | `PipelineResult` with `outcome="error"` or null | error message |

### POST /api/v1/investigate (deprecated)

Legacy alert-based stub. Takes an `InvestigationRequest` body, returns `InvestigationResult`. Kept for backward compatibility; marked `deprecated=True` in OpenAPI.

### Frontend Integration Cheat Sheet

```
1. On page load:
   GET /api/v1/clients  →  populate dropdown with client_name (client_id as value)

2. On "Run Investigation" click:
   POST /api/v1/investigate/{client_id}
     →  show spinner
     →  on 200: render PipelineResult panels
     →  on 409: "already running"
     →  on 502: show error

3. To check a previous run:
   GET /api/v1/investigate/{client_id}/status
     →  "not_started": show "Run Investigation" button
     →  "running": show spinner
     →  "completed": render cached PipelineResult
```
