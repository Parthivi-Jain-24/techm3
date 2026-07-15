# Project Memory

## Last audited
- **Date**: 2026-07-14
- **Reference playbook**: `entity-intelligence-engineer-playbook.md` (in Downloads folder)
- **Hackathon**: Tech Mahindra CODE Hackathon — Continuous KYC Autonomous Auditor

## Source of truth
- This project is based on the attached "Entity Intelligence Engineer — Build Playbook".
- The hackathon scope is a Continuous KYC Autonomous Auditor focused on sanctions screening, adverse media, and hidden ownership risk.

## Ownership area
- OpenSanctions + OFAC SDN ingestion and normalization.
- Hybrid fuzzy and semantic entity matching.
- Alias, DOB, nationality, and company-context resolution.
- Adverse-media extraction with prompt-injection defenses.
- UBO ownership graph traversal.

## Core contracts
- Every finding must emit `evidence_id`, `entity_id`, `source`, `confidence`, and `retrieved_at`.
- Every match should include component scores and a classification bucket.
- Evidence must be traceable enough for downstream SAR generation and audit logging.
- Evidence IDs are auto-generated via `EvidenceIdGenerator` (thread-safe, format `EVD-NNN`).

## Target data shapes
- `SanctionedEntity`: entity_id, name, aliases, dob, nationality, entity_type, **company**, topics, source_list, source_url, context.
- `EvidenceRecord`: evidence_id, entity_id, matched_against, match_score, component_scores, classification, source, retrieved_at, metadata.
- `AdverseMediaFinding`: evidence_id, entity_id, source_url, extracted_claims, injection_attempt_detected, injection_details, retrieved_at, metadata.
- `OwnershipEdge`: owner_id, owned_id, percentage.
- `EntityRecord`: entity_id, name, context, metadata.
- `Claim`: claim, supported, confidence.
- `MatchComponentScores`: name, alias, dob, nationality, company, context.

## Matching logic
- Never rely on exact-name matching alone.
- Use candidate retrieval (via `CandidateIndex` with 4-char prefix keys), fuzzy name and alias scoring, DOB and nationality checks, semantic context similarity, then confidence bucketing.
- Thresholds: `CONFIRMED_MATCH >= 0.85`, `POSSIBLE_MATCH >= 0.55`, otherwise `LIKELY_FALSE_POSITIVE`.
- Weights: 0.30 name + 0.15 alias + 0.15 dob + 0.10 nationality + 0.15 company + 0.15 context.
- Context similarity uses `sentence-transformers` (all-MiniLM-L6-v2) when available, falls back to fuzzy matching.

## Adverse media safety
- Treat article text as untrusted data only.
- Use strict delimiters, sanitization, and a guard pass to reject unsupported claims.
- Detect and flag prompt-injection language such as instruction overrides.
- Suspicious patterns currently checked: "ignore previous instructions", "ignore all prior instructions", "system:", "you are now", "act as".

## UBO graph
- Use a directed ownership graph with NetworkX.
- Walk outward from a customer node through ownership layers.
- Flag any chain that resolves to confirmed or possible sanctions risk.
- Respects max_depth parameter (default 5).

## Current status (as of 2026-07-14)
### What works
- All **8 modules** exist and import correctly (schemas, scoring, resolution, adverse_media, ubo_graph, evidence, data_loader, cli).
- **45 unit tests pass** covering scoring, evidence IDs, candidate retrieval, resolution pipeline, adverse media, and all data loaders.
- CLI demo runs both playbook §9 regression test cases successfully.
- True-positive test: **0.8954 -> CONFIRMED_MATCH** (was 0.8288 POSSIBLE_MATCH before fix).
- False-positive test: **0.4264 -> LIKELY_FALSE_POSITIVE**.
- Batch resolution via `CandidateIndex` works end-to-end.
- Evidence IDs auto-increment correctly across all modules.
- All data loaders work against real and sample datasets.

### Datasets available locally
- `data/clients_with_fatf_ofac.csv` — **2,000 clients** with PEP, sanctions, FATF, OFAC flags, ownership opacity scores.
- `data/transactions_with_fatf_ofac.csv` — **50,000 transactions** with OFAC match, structuring, rapid movement, trade mispricing flags.
- `data/gdpr_articles.csv` + `data/gdpr.json` — GDPR regulation articles for compliance reference.
- `data/sanctions/sample_ofac_sdn.csv` — 17 sample OFAC SDN entries (individuals + companies).
- `data/sanctions/sample_ofac_alt.csv` — 15 aliases linked to SDN entries.
- `data/sanctions/sample_opensanctions.csv` — 22 sample OpenSanctions entries.
- `data/articles/clean_article.txt` — Clean adverse media article (no injection).
- `data/articles/adversarial_article.txt` — Adversarial article with embedded prompt injections (demo showpiece).
- `data/articles/adverse_hit_article.txt` — Legitimate adverse media with money laundering allegations.
- `data/ubo/showcase_structure.json` — 3-layer hidden-UBO chain (sanctioned individual at bottom).
- `data/ubo/simple_structure.json` — Clean corporate structure (control case).
- `scripts/download_data.py` — Downloads real OFAC SDN + OpenSanctions data.

### Previously fixed issues (2026-07-14)
- **Scoring gap fixed**: Added `company` field to `SanctionedEntity`. Score jumped from 0.8288 to 0.8954.
- **Evidence IDs**: Created `evidence.py` with thread-safe `EvidenceIdGenerator`. Wired into resolution + adverse_media.
- **Candidate retrieval wired**: Built `CandidateIndex` class using `candidate_retrieval_key()`. Added `resolve_against_candidates()` batch function.
- **Semantic embeddings**: `contextual_similarity()` in scoring.py uses sentence-transformers when available, falls back to fuzzy matching.
- **Data layer built**: `data_loader.py` parses OFAC SDN, OpenSanctions, clients, transactions, UBO structures, articles, and GDPR data.
- **Demo fixtures created**: adversarial article, adverse hit article, clean article, showcase UBO chain, clean UBO structure.

### Remaining gaps
- No actual LLM call for adverse media claim extraction or guard pass.
- No integration functions (`get_sanctions_matches()`, `get_adverse_media()` for Part 3).
- No audit event emission for Part 1.
- `gcapi.dll` in data/ folder is unknown — confirm if needed or remove.

## Build direction
- Keep the first implementation small and testable.
- Prefer simple Python modules and plain JSON contracts before adding persistence or model infrastructure.
- Implementation order: schemas -> scoring -> resolution -> adverse media -> graph traversal -> integration services.
- Next priorities: wire LLM for adverse media extraction, build integration APIs, add audit event emission.

