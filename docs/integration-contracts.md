# Integration Contracts — Ingestion + Entity Intelligence (Workstreams A & B)

This document defines the two integration-boundary contracts **produced by my
pipeline** and the conventions downstream workstreams rely on. It is the
authoritative, code-backed definition for these two contracts.

> **Reconciliation note.** An earlier team-wide placeholder,
> [`docs/architecture/integration-contracts.md`](architecture/integration-contracts.md),
> sketched rough JSON for these records using different field names and a 0–1
> confidence scale (`display_name`, `match_type`, `match_confidence: 0.0`,
> `evidence_ids`, `detected_at`). The Pydantic models below are the current,
> producer-owned definitions and **supersede** those sketches. Consumers should
> align to this document. Because these are shared contracts, any change to
> field names/types/scale must be coordinated with consuming workstreams.

The models live in `backend/app/schemas/` (not duplicated under feature
modules) and are implemented in Phase 1 as **shape-only** contracts — no
ingestion, screening, matching, or scoring logic exists yet.

---

## Pipeline position

```
Secure KYC Ingestion  ──►  NormalizedKYCEntity
                                   │
                                   ▼
                          Entity Intelligence  ──►  EntityIntelligenceResult
                                   │
                                   ▼
              Risk Intelligence ► Investigation ► Human Review / Dashboard
```

---

## Contract 1 — `NormalizedKYCEntity`

Canonical normalized customer profile produced by secure ingestion.
Source: `backend/app/schemas/kyc.py`.

| Field | Type | Notes |
|---|---|---|
| `client_id` | string, **required, non-blank** | Canonical customer identifier. |
| `client_name` | string, **required, non-blank** | Normalized legal/display name. |
| `client_type` | string, required | e.g. `corporate`, `individual`. |
| `country` | string, required | Primary jurisdiction (e.g. ISO code). |
| `sector` | string, required | Business sector / industry. |
| `sector_risk` | enum `low` \| `medium` \| `high` | Ordinal inherent **sector** risk band, not customer risk. **Changed in Phase 2** (was `0–100`). |
| `pep_flag` | boolean (default `false`) | Politically Exposed Person. |
| `sanctions_flag` | boolean (default `false`) | Source-profile sanctions association. |
| `fatf_country_flag` | boolean (default `false`) | FATF high-risk / monitored jurisdiction. |
| `aliases` | string[] (default `[]`) | Known alternative names. |
| `created_at` | tz-aware datetime | **Record** timestamp: when the pipeline created this normalized record (UTC). Not a source/customer date. |
| `updated_at` | tz-aware datetime | **Record** timestamp: when the pipeline last updated this record (UTC). |

> **Phase 2 schema change (coordinate with consumers).** `sector_risk` changed
> from numeric `0–100` to the ordinal enum `low/medium/high`, because the real
> KYC dataset encodes it categorically (High/Medium/Low); a numeric mapping
> would invent false precision. See docs/kyc-ingestion.md §8.

Rules: sensitive raw identifiers (government IDs, full account numbers) are
**not** part of this contract — data minimization is applied in ingestion
before a record leaves Workstream A. The source dataset also carries
`ofac_country_flag`, `sectoral_sanctions_flag`, and `ownership_opacity_score`,
which are **not yet** in this contract (candidates for a future coordinated
extension); ingestion reports them as `additional_source_columns`.

---

## Contract 2 — `EntityIntelligenceResult`

Canonical output of screening a customer against a sanctions list, OFAC SDN,
another watchlist, or adverse media. Source:
`backend/app/schemas/entity_intelligence.py`.

| Field | Type | Notes |
|---|---|---|
| `result_id` | string, **required, non-blank** | Stable id for this result. |
| `client_id` | string, **required, non-blank** | Canonical customer identifier. |
| `source_type` | string, required | e.g. `sanctions`, `watchlist`, `adverse_media`. |
| `source_name` | string, required | e.g. `OFAC SDN`, `OpenSanctions`. |
| `matched_entity_name` | string \| null | Matched external entity name; `null` if none. |
| `match_confidence` | number `0–100` | **Entity-identity-resolution** confidence only. |
| `decision` | enum | See decisions below. |
| `matched_attributes` | string[] (default `[]`) | Attributes that drove the match (explainability). |
| `evidence_references` | string[] (default `[]`) | Pointers to supporting evidence (traceability). |
| `evaluated_at` | tz-aware datetime | When evaluated (UTC). |

**Decisions:** `confirmed_match`, `likely_match`, `needs_review`,
`likely_false_positive`, `no_match`.

### Why the boundaries matter

`match_confidence` measures **how sure we are the external record refers to the
same entity** — it is *not* the customer's risk score, and this model
deliberately carries no risk field. A high **name** similarity must never, by
itself, become `confirmed_match`; identity has to be corroborated by other
attributes (country, role, DOB, organization…). Example: KYC "Rahul Sharma,
Mumbai, Director of ABC Technologies" vs. external "Rahul Sharma, Delhi, Owner
of XYZ Exports, arrested for fraud" — same name, almost certainly a different
person. The resolution algorithms that enforce this arrive in later phases.

---

## Integration conventions

1. `client_id` is the canonical customer identifier across every workstream.
2. Backend / API JSON uses **snake_case**.
3. Entity **match confidence** uses a **0–100** scale.
4. Entity match confidence is **separate from customer risk** (a different
   workstream owns risk scoring).
5. A **name match is never automatically a confirmed match**.
6. **External content is untrusted input** (news, sanctions files, uploads,
   web text) — treated as data, never as instructions.
7. Material entity-intelligence findings should reference **evidence**.
8. My modules must not depend on teammates' internal implementations.
9. Integration happens through **explicit contracts and APIs**, not shared
   internal code.
10. Shared contracts are **not duplicated** under feature modules; they live in
    `backend/app/schemas/`.

## Privacy-safe representations (Phase 3)

The canonical `NormalizedKYCEntity` is for **trusted internal processing**. When
a KYC record crosses a boundary (logs, entity screening, human review, AI
agents, external responses), consumers should use a **context-minimized**
representation, not the raw entity:

```python
from app.privacy import minimize_kyc_entity, ProcessingContext
payload = minimize_kyc_entity(entity, ProcessingContext.ENTITY_SCREENING)
```

These return JSON-safe dicts (never the raw model), omit fields the context
doesn't need, mask sensitive ones, and **fail closed** on unknown contexts. See
`docs/privacy-and-data-governance.md` for the per-context field matrix. Notably,
`ENTITY_SCREENING` preserves only identity-matching fields (`client_id`,
`client_name`, `aliases`, `country`, `client_type`) — entity resolution never
receives risk/compliance signals.
