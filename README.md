# ProjectTechM

Scaffold for the **Continuous KYC Autonomous Auditor** described in the entity-intelligence playbook.

## What this project covers

- Sanctions and watchlist entity normalization
- Hybrid entity resolution with fuzzy + contextual scoring hooks
- Evidence-first output contracts for downstream risk and SAR workflows
- Adverse-media extraction with prompt-injection defense hooks
- Ownership graph traversal for hidden-UBO detection

## Suggested structure

- `src/projecttechm/schemas.py` - evidence and entity contract models
- `src/projecttechm/scoring.py` - match scoring helpers and bucketing
- `src/projecttechm/resolution.py` - entity candidate resolution pipeline
- `src/projecttechm/adverse_media.py` - article sanitization and extraction guardrails
- `src/projecttechm/ubo_graph.py` - ownership graph traversal helpers
- `src/projecttechm/cli.py` - demo entry point

## Run

```bash
python -m venv .venv
.\.venv\Scripts\activate
pip install -e .[dev]
```

### API

```bash
uvicorn projecttechm.api:app --reload
```

Then open **http://127.0.0.1:8000/docs** for Swagger UI — every endpoint is
runnable from the browser via "Try it out", pre-filled with working examples.

| Endpoint | Purpose |
|---|---|
| `GET /health` | Loaded dataset counts; shows whether semantic matching is active |
| `POST /screen` | Screen any KYC entity against the sanctions index |
| `GET /customers` | Page the client book to find IDs |
| `GET /customers/{id}/sanctions-matches` | Playbook §7 contract for Part 3 |
| `POST /adverse-media/analyze` | Analyze an article; flags prompt injection |
| `GET /customers/{id}/adverse-media` | Playbook §7 contract for Part 3 |
| `GET /ubo/structures` | List ownership graphs |
| `POST /ubo/trace` | Walk an ownership chain for hidden sanctioned parties |

### CLI demo

```bash
projecttechm-demo
```

### Tests

```bash
pytest                                   # 165 tests
pytest tests/test_real_data.py -q        # real-list tests (skip if not downloaded)
```

### Judge evaluation

```bash
python scripts/evaluate.py               # exits non-zero if a hard check fails
python scripts/verify_llm.py             # needs a provider key; free on NVIDIA/Groq
```

`verify_llm.py` is the one that matters before relying on the adverse-media
agent: it exercises both passes against the **real** model, checks the guard
drops a claim the source contradicts ("convicted" when the source says *not
charged*), and confirms the agent does not obey an article that orders it to
report the entity as clean. Exits 2 if no backend is configured.

Runs the checks a judge would run — data provenance, the §9 regression cases,
the evidence contract, injection variants the demo article does *not* contain,
the hidden-UBO chain, and the §7 integration contracts. Scope gaps are reported
as WARN rather than hidden.

## Sanctions data

```bash
python scripts/download_data.py      # real OFAC SDN + ALT + OpenSanctions
```

| File | Rows | Notes |
|---|---|---|
| `ofac_sdn.csv` | 19,156 | Published **without a header row**; `-0-` means null |
| `ofac_alt.csv` | 20,336 | Aliases — 9,892 SDN entities get one |
| `opensanctions_targets.csv` | 1.32M | 488 MB; ~1.28M are KYC-screenable schemas |

**Full coverage is the default**: all 1,294,769 screenable entities, ~40s
startup, ~1.1 GB resident. Screening a subset by default is the wrong default
for a compliance system — a bounded index cannot find a party it never indexed.

For fast `uvicorn --reload` iteration, cap the row count (200000 loads in ~2s).
Any cap is disclosed, never silent: `GET /health` reports
`sanctions_coverage_complete: false` and marks the source `truncated`.

| Env var | Default | Meaning |
|---|---|---|
| `PROJECTTECHM_SANCTIONS_MODE` | `both` | `both` \| `real` \| `sample` |
| `PROJECTTECHM_OPENSANCTIONS_LIMIT` | *(unset = all 1.32M)* | Row cap for dev speed |
| `PROJECTTECHM_DATA_DIR` | `./data` | Override the data root |

**Modes matter.** The playbook §9 cases and the hidden-UBO showcase are
synthetic — "Mohammed Al Rashid" / CUST-2041 / ABC Holdings exist only in
`sample_*.csv`, never in real OFAC. `real` alone silently evicts the demo;
`sample` alone hides real-world scale. `both` loads each, tagging fixture
entities `(SAMPLE FIXTURE)` so a synthetic record can never pass as a genuine
listing. The test suite pins to `sample` for determinism.

## Semantic matching

`contextual_similarity()` uses `all-MiniLM-L6-v2` when installed and silently
falls back to fuzzy otherwise — `GET /health` reports which via
`semantic_matching_available`. It materially changes results, so prefer it:

```bash
pip install -e .[ml]
```

Fuzzy rates the §9 *false* positive's context (0.49) **above** the true match's
(0.31), because it compares characters rather than meaning. Embeddings invert
that (0.61 vs 0.24) and lift the hidden-UBO showcase to CONFIRMED_MATCH.

CPU is enough: the scorer prunes candidates whose other five components cannot
reach the threshold even with a perfect context, so a real 1,455-candidate query
embeds ~161 of them, and embeddings are cached per string.

## Adverse-media agent (playbook §4)

The two-pass shape is the requirement; the vendor is not. Pick a backend:

| `PROJECTTECHM_LLM_PROVIDER` | Model | Key | Cost |
|---|---|---|---|
| `ollama` *(default)* | `qwen2.5:7b` | *(none)* | **free, local, offline, zero egress** |
| `nvidia` | `meta/llama-3.3-70b-instruct` | `NVIDIA_API_KEY` | free credits — [build.nvidia.com](https://build.nvidia.com) |
| `groq` | `llama-3.3-70b-versatile` | `GROQ_API_KEY` | free tier — [console.groq.com](https://console.groq.com) |
| `openrouter` | `llama-3.3-70b-instruct:free` | `OPENROUTER_API_KEY` | free tier |
| `anthropic` | `claude-opus-4-8` | `ANTHROPIC_API_KEY` | paid |
| `none` | — | — | off; heuristic extractor |

**Local by default.** The agent's input is public article text, but the free
hosted tiers are explicit that they are not for confidential data, and a KYC
system should not rest on a reviewer trusting that distinction. Local inference
removes the question entirely: no third-party processor, no egress, no key, no
rate limit — and the demo survives conference wifi.

```bash
winget install Ollama.Ollama
ollama pull qwen2.5:7b
python scripts/verify_llm.py          # verify the model before trusting it
uvicorn projecttechm.api:app
```

Verified on this stack: **12/12**, including the guard dropping "convicted of
money laundering" when the source says *not been charged*, and the agent
refusing an article that orders it to report the entity as clean.

`is_configured()` **probes** a local backend rather than assuming it — Ollama
needs no key, so config alone would let `/health` claim the agent is available
for a server that was never started, or one with the model not pulled.

Override the model with `PROJECTTECHM_LLM_MODEL`, or the endpoint with
`PROJECTTECHM_LLM_BASE_URL` (anything OpenAI-compatible: vLLM, LM Studio, …).

### What the LLM is allowed to see

**Only public news article text.** Customer records, the sanctions index,
transactions, and entity IDs never reach a model — entity resolution, scoring,
and UBO tracing are entirely local computation. The LLM's only job is reading
articles that are already public.

That property is **enforced, not assumed**. Free LLM tiers are explicit that they
are not for confidential data — NVIDIA's own guidance for build.nvidia.com is not
to upload personal or confidential information, and reporting on the free tier
[disagrees](https://www.stork.ai/blog/nvidias-free-ai-the-hidden-cost) about
whether inputs are retained or used for training. So `egress.py` scans every
outbound string at the `Backend` boundary — the one place every provider must
cross — and applies a policy:

| `PROJECTTECHM_LLM_EGRESS` | Behaviour |
|---|---|
| `block` *(default)* | Refuse to send. A compliance system fails closed. |
| `redact` | Mask identifiers as `[REDACTED:<kind>]`, send the rest |
| `allow` | Send unchanged — only sane for a local backend |

Caught: internal IDs (`CLIENT-`/`CUST-`/`EVD-`), emails, phones, card numbers,
IBANs, SSNs, Aadhaar, passport numbers.
**Never redacted: personal names** — they are the subject of adverse-media
analysis and already public in the article. Masking them would defeat the agent.

A local backend (`ollama`, or any `localhost` endpoint) is **exempt**: nothing
leaves the host, so there is no third party to withhold from.

`GET /health` reports `llm_egress_policy` and the resolved `llm_provider`.

### If nothing may leave the machine at all

```bash
# install ollama, then:
ollama pull qwen2.5:7b
PROJECTTECHM_LLM_PROVIDER=ollama PROJECTTECHM_LLM_MODEL=qwen2.5:7b \
  uvicorn projecttechm.api:app
```

Zero data egress, no key, no rate limit, works offline. The honest tradeoff: a
7–8B model is meaningfully weaker at the guard's judgement task than a 70B. Run
`verify_llm.py` against it before trusting it.

**Anthropic guarantees schema-valid JSON; open models do not.** They wrap output
in markdown fences, add preambles, or drop keys. The `openai_compat` backend
therefore assumes nothing: it strips fences, extracts the outermost object,
validates required keys, and retries once with the parse error fed back. Two
failures raise — a guard returning garbage is worse than one that fails loudly.

**Quality is not equal across backends.** The guard's job is judgement (does this
source support this claim?), and that is exactly where a free 70B differs most
from a frontier model. `verify_llm.py` tests the judgement, not the plumbing —
re-run it whenever you change provider or model.

Two passes:

1. **Extraction** — the article is wrapped in `<article>` delimiters (a nested
   `</article>` is escaped so it cannot close its own block) and the system
   prompt states the content is data, never instructions.
2. **Guard** — a second, independent call receives the first pass's claims *plus
   the original source* and rules on whether the source supports each one.
   Unsupported claims are dropped, and the drop is reported
   (`metadata.claims_dropped_by_guard`), never silently swallowed.

The guard is an allowlist: a claim with no verdict is dropped. Injection is
flagged if **either** the pattern matcher or the model spots it.

`GET /health` reports `llm_adverse_media_available`. With no backend, extraction
degrades to the keyword heuristic and says so (`llm_extraction: "unavailable"`).
An LLM error mid-run also falls back, recording `metadata.llm_error` — an LLM
outage must not take screening down. Findings carry `provider` and `model`, so
a claim from a local 8B is never mistaken for one from a frontier model.

## Audit events (playbook §7 → Part 1)

Part 2 emits; Part 1 owns the durable log. Events fire for
`ENTITY_MATCH_CALCULATED` (per returned match, not per candidate scored),
`ADVERSE_MEDIA_AGENT_RUN`, and `PROMPT_INJECTION_DETECTED`.

```bash
GET /audit/events    # newest last, hash-chained, bounded (reports `dropped`)
GET /audit/verify    # recompute the chain; names the entry where it breaks
```

Until Part 1 registers its sink via `set_audit_sink()`, events land in a bounded
in-process sink that hash-chains them (SHA-256 over each event plus its
predecessor's hash). Mutate a stored event and `/audit/verify` flips to
`valid: false` naming the entry — the §10 tamper-detection demo.

## Known gaps

- **`verify_llm.py` result is model-specific.** The 12/12 above is qwen2.5:7b on
  Ollama. Judgement is exactly what varies between models, so re-run it whenever
  you change `PROJECTTECHM_LLM_PROVIDER` or `PROJECTTECHM_LLM_MODEL`. The test
  suite pins the agent off (`PROJECTTECHM_LLM_PROVIDER=none`) so results never
  depend on what this machine has installed.
- **Adverse-media findings are in-process only**, not persisted.

## Notes

The detailed project memory is captured in `memory.md` and `documentation.md` so another AI can continue implementation without re-reading the playbook.
