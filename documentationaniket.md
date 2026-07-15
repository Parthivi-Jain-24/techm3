# Project Documentation

## Purpose
ProjectTechM is a Python scaffold for a hackathon-grade Continuous KYC Autonomous Auditor. It is designed so that another AI or developer can continue the implementation from the same contracts without revisiting the original playbook.

## Reference
- **Playbook**: `entity-intelligence-engineer-playbook.md` (located in `C:\Users\anike\Downloads\`)
- **Hackathon**: Tech Mahindra CODE Hackathon
- **Last updated**: 2026-07-14

## Project structure

```
projecttechm/
├── src/projecttechm/
│   ├── __init__.py          # Package init, version 0.1.0
│   ├── schemas.py           # Pydantic models for all data contracts
│   ├── scoring.py           # Fuzzy matching, semantic context, weights, classification
│   ├── resolution.py        # Entity resolution pipeline + CandidateIndex
│   ├── evidence.py          # Thread-safe auto-incrementing evidence ID generator
│   ├── adverse_media.py     # Article sanitization and prompt-injection detection
│   ├── ubo_graph.py         # Ownership graph traversal with NetworkX
│   └── cli.py               # Demo entry point with both §9 regression test cases
├── tests/
│   └── test_scoring.py      # 22 unit tests (scoring, evidence, resolution, adverse media)
├── pyproject.toml            # Build config, dependencies, script entry points
├── pytest.ini                # Pytest config
├── memory.md                 # Quick-reference project state for AI continuation
├── documentation.md          # This file — detailed documentation
└── README.md                 # User-facing project overview
```

## Functional areas

### 1. Sanctions screening
**Status**: Schema defined with `company` field, no data ingestion yet.

Inputs:
- OpenSanctions targets list (`data/sanctions/opensanctions_targets.csv` — not yet downloaded)
- OFAC SDN list (`data/sanctions/ofac_sdn.csv` — not yet downloaded)

Outputs:
- Normalized sanctioned entity records (`SanctionedEntity` model with company field)
- Candidate retrieval indexes (`CandidateIndex` with 4-char prefix keys)
- Evidence records for any positive or possible match

**What's missing**: CSV parser, data download script, queryable store.

### 2. Entity resolution
**Status**: Full pipeline works end-to-end. Scoring accuracy verified.

Pipeline:
1. KYC entity input (as dict)
2. ✅ Candidate retrieval (`CandidateIndex` groups entities by 4-char prefix, falls back to full list)
3. ✅ Name and alias similarity (via rapidfuzz — ratio, partial_ratio, token_sort_ratio, token_set_ratio)
4. ✅ DOB, nationality, and company checks (exact-or-unknown matching, company uses dedicated field)
5. ✅ Contextual similarity (semantic via sentence-transformers when available, fuzzy fallback)
6. ✅ Confidence scoring and classification (weighted formula + threshold bucketing)

**Verified scores** (playbook §9):
- True positive: **0.8954 → CONFIRMED_MATCH** (target: ~0.94)
- False positive: **0.4264 → LIKELY_FALSE_POSITIVE** (target: ~0.31)

### 3. Adverse media agent
**Status**: Sanitization layer + evidence IDs work. No LLM integration.

Pipeline:
- ✅ Sanitize article and detect prompt-injection patterns
- ❌ LLM extraction pass (no API call implemented)
- ❌ Guard LLM pass (no second verification call)
- ✅ Build structured finding with auto-generated evidence IDs

Security requirements:
- ✅ Detects prompt injection attempts (5 suspicious patterns)
- ✅ Ignores instructions embedded inside articles (by design in SYSTEM_PROMPT)
- ✅ Preserves source text and retrieval metadata
- ❌ No rehearsed adversarial demo article

### 4. UBO ownership graph
**Status**: Core traversal works. No demo fixtures.

Pipeline:
- ✅ Model ownership as a directed graph (NetworkX DiGraph)
- ✅ Traverse ownership paths from a customer entity (uses `nx.descendants`)
- ✅ Resolve every node in the chain against sanctions data
- ✅ Flag a chain if any layer is a confirmed or possible match
- ✅ Respects max_depth parameter
- ❌ No pre-built mock corporate structure with hidden-UBO showcase

### 5. Evidence contract
**Status**: Fully functional with auto-incrementing IDs.

Every major output includes:
- ✅ `evidence_id` (auto-generated via `EvidenceIdGenerator`, format `EVD-NNN`)
- ✅ `entity_id`
- ✅ `source`
- ✅ `confidence` (via `match_score`)
- ✅ `retrieved_at`

Evidence ID generator (`evidence.py`):
- Thread-safe via `threading.Lock`
- Configurable prefix and start value
- `next_id()`, `peek()`, `reset()` methods
- Module-level default instance: `evidence_id_gen`

## Module details

### schemas.py
- 7 Pydantic models: `SanctionedEntity`, `MatchComponentScores`, `EvidenceRecord`, `Claim`, `AdverseMediaFinding`, `OwnershipEdge`, `EntityRecord`
- `SanctionedEntity` now includes `company` field (added 2026-07-14)

### scoring.py
- `normalized_similarity()` — multi-strategy fuzzy match (best of 4 rapidfuzz algorithms)
- `alias_similarity()` — max similarity across an alias list
- `exact_or_unknown_match()` — binary match with 0.5 for unknown
- `contextual_similarity()` — **semantic** via sentence-transformers when available, fuzzy fallback. Returns 0.3 for missing context (neutral per playbook)
- `is_semantic_available()` — check if sentence-transformers is loaded
- `classify()` — threshold bucketing
- `weighted_match_score()` — playbook's exact 6-component weighted formula

### resolution.py
- `candidate_retrieval_key()` — 4-char alphanumeric prefix key
- `CandidateIndex` — pre-indexed sanctions list grouped by prefix key. Indexes both primary names and aliases. Falls back to full list if no prefix match found
- `build_component_scores()` — computes all 6 components. Uses `candidate.company` for company matching (not context)
- `resolve_entity()` — full single-candidate pipeline with auto-generated evidence IDs
- `resolve_against_candidates()` — batch resolution via CandidateIndex, returns only confirmed/possible matches sorted by score

### evidence.py
- `EvidenceIdGenerator` — thread-safe counter with configurable prefix/start
- `evidence_id_gen` — module-level default instance used by resolution.py and adverse_media.py

### adverse_media.py
- `SYSTEM_PROMPT` — designed per playbook (data-only, strict JSON output, injection awareness)
- `SUSPICIOUS_PATTERNS` — 5 prompt-injection patterns
- `sanitize_article()` — returns (text, injection_detected, details)
- `build_finding()` — constructs `AdverseMediaFinding` with auto-generated evidence ID

### ubo_graph.py
- `find_sanctioned_in_chain()` — walks all descendants, resolves each against sanctions, returns findings with ownership paths
- `add_entity()` — adds an `EntityRecord` node to the graph

### cli.py
- Runs both playbook §9 regression tests (true positive + false positive)
- Demonstrates batch resolution via `CandidateIndex`
- Resets evidence ID counter for clean demo runs

## Integration contracts (from playbook §7)

| Contract | Target | Status |
|----------|--------|--------|
| `get_sanctions_matches(customer_id)` | Part 3 (Risk) | ❌ Not implemented |
| `get_adverse_media(customer_id)` | Part 3 (Risk) | ❌ Not implemented |
| Evidence with `evidence_id`, `source`, `confidence`, `retrieved_at` | Part 4 (SAR) | ✅ Working |
| Audit events: `ENTITY_MATCH_CALCULATED`, `ADVERSE_MEDIA_AGENT_RUN`, `PROMPT_INJECTION_DETECTED` | Part 1 (Audit) | ❌ Not implemented |

## Suggested implementation order
1. ✅ Schemas and evidence contracts
2. ⚠️ Sanctions normalization and candidate retrieval (retrieval done, CSV loader missing)
3. ✅ Entity scoring and classification
4. ⚠️ Adverse-media extraction and injection defenses (sanitization done, LLM missing)
5. ✅ Ownership graph traversal (needs demo data)
6. ❌ Integration points for audit and SAR generation

## Continuation rules for future AI
- Keep outputs JSON-serializable.
- Preserve evidence IDs across all modules — use `evidence_id_gen` from evidence.py.
- Do not weaken the prompt-injection guard.
- Do not replace fuzzy or semantic matching with exact name matching only.
- Prefer small deterministic helpers before introducing heavier infrastructure.
- The `company` field on `SanctionedEntity` is critical for accurate scoring — do not remove it.
- Any new module should follow the existing pattern: import from schemas, return typed models.

## Demo expectations
- ✅ One true positive sanctions match (0.8954 CONFIRMED_MATCH)
- ✅ One clear false positive (0.4264 LIKELY_FALSE_POSITIVE)
- ❌ One adversarial article with a blocked injection attempt
- ❌ One hidden-UBO chain that reveals risk through ownership layers

## Tech stack
- **Python**: 3.11+
- **Build**: hatchling
- **Core deps**: pydantic >=2.7, rapidfuzz >=3.9, networkx >=3.3
- **ML (optional)**: sentence-transformers >=3.0, torch >=2.3
- **Dev**: pytest >=8.0, ruff >=0.6
