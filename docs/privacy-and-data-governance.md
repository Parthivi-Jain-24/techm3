# Privacy & Data Governance (Phase 3)

## 1. Scope

Phase 3 adds **privacy-aware engineering controls** for normalized KYC data:
deterministic field classification, masking, keyed pseudonymization, purpose-
based data minimization, safe logging/agent representations, and record-level
data-quality assessment.

These are **engineering controls designed to support privacy and governance
requirements**. This is **not** a legal-compliance certification — we do not
claim "GDPR compliant" or "fully compliant with all privacy regulations". GDPR /
PrivacyQA / OPP-115 are privacy/governance *resources*, not AML risk-scoring,
sanctions-screening, or SAR standards.

Code lives under `backend/app/privacy/`:
`classification/`, `masking/`, `minimization/`, `quality/`, `contexts.py`,
`errors.py`.

## 2. Classification vs. masking vs. minimization

| Concept | Meaning | In code |
|---|---|---|
| **Classification** | static sensitivity label per field | `classification/` |
| **Masking** | field **stays present**, value obscured | `Treatment.MASK` → `masking/` |
| **Minimization** | field **omitted entirely** (consumer doesn't need it) | `Treatment.OMIT` |

Rule of thumb: **prefer omission** when a field isn't needed; **mask** only when
the field's existence or partial value is operationally useful. None of these
transformations mutate the canonical `NormalizedKYCEntity` — they return derived
JSON-safe representations.

## 3. Classification taxonomy

Ordered least → most sensitive: `PUBLIC`, `INTERNAL`, `PERSONAL`, `SENSITIVE`,
`HIGHLY_SENSITIVE`. Classification is **explicit and deterministic** — never
decided by an LLM. Unknown fields **fail closed** to `HIGHLY_SENSITIVE` + redact.

## 4. Classification of the actual canonical KYC fields

| Field | Class | Default mask | Rationale |
|---|---|---|---|
| `client_id` | INTERNAL | pseudonymize | surrogate id; small value space → keyed pseudonym in logs |
| `client_name` | PERSONAL | mask_name | may be a person's name (or org legal name) |
| `client_type` | INTERNAL | none | business categorization |
| `country` | INTERNAL | none | jurisdiction/geo context |
| `sector` | INTERNAL | none | industry classification |
| `sector_risk` | INTERNAL | none | inherent sector band (business attribute) |
| `pep_flag` | SENSITIVE | redact | political-exposure profiling signal |
| `sanctions_flag` | SENSITIVE | redact | sanctions-association compliance signal |
| `fatf_country_flag` | INTERNAL | none | country-level risk flag (not personal) |
| `aliases` | HIGHLY_SENSITIVE | mask_name | alternative/hidden identities |
| `created_at` | INTERNAL | none | record-management metadata |
| `updated_at` | INTERNAL | none | record-management metadata |

**Person vs. organization:** name masking uses `client_type` — `Individual`
names are initialled per token (`John Smith → J*** S****`); organization names
keep the first token (`Acme Global Holdings → Acme G***** H*******`).

## 5. Processing contexts

`INTERNAL_PROCESSING`, `LOGGING`, `ENTITY_SCREENING`, `HUMAN_REVIEW`,
`AGENT_CONTEXT`, `EXTERNAL_RESPONSE`. **Unknown context → fail closed** (raises
`UnknownProcessingContextError`; never returns the full record). Any field not
listed for a context is **omitted** (fail-closed), so a newly added canonical
field can't leak into an existing context.

> These are representation boundaries only. **Access-control enforcement** (who
> may request which context) is Phase 4 (authentication/RBAC) — not implemented
> or claimed here.

## 6. Field policy by processing context

`R` = raw, `M` = masked, `·` = omitted.

| Field | INTERNAL | LOGGING | ENTITY_SCREENING | HUMAN_REVIEW | AGENT | EXTERNAL |
|---|---|---|---|---|---|---|
| client_id | R | M | R | M | M | M |
| client_name | R | · | R | M | · | · |
| client_type | R | R | R | R | R | R |
| country | R | R | R | R | R | · |
| sector | R | · | · | R | · | · |
| sector_risk | R | R | · | R | R | · |
| pep_flag | R | · | · | R | · | · |
| sanctions_flag | R | · | · | R | · | · |
| fatf_country_flag | R | · | · | R | · | · |
| aliases | R | · | R | M | · | · |
| created_at | R | · | · | R | · | · |
| updated_at | R | · | · | R | · | · |

`ENTITY_SCREENING` keeps identity-matching fields (id, name, aliases, country,
type) and drops risk/compliance signals — entity resolution is not risk scoring.

## 7. Logging-safe behavior

`to_log_safe_dict(entity)` = `LOGGING` context: pseudonymized `client_id`, coarse
`client_type` / `country` / `sector_risk`. **No** names, aliases, or sensitive
flags, and never the full entity.

## 8. Agent-safe behavior

`to_agent_safe_dict(entity)` defaults to `AGENT_CONTEXT` — aggressively
minimized (pseudonymous id + coarse context). The full canonical record is
**never** exposed to an agent by default; a specific, bounded task must request
more explicitly. Future agents must be **authenticated, authorized, validated,
bounded, and audited**, and must never have unrestricted database access.

## 9. Pseudonymization

`pseudonymize(value, key)` = HMAC-SHA256(key, value) → `anon_<16 hex>`. Keyed
(not a plain hash) because identifier value spaces can be small/guessable. Key
resolution: explicit arg → `PSEUDONYMIZATION_KEY` env → clearly-insecure **dev
fallback** (documented, non-secret, local-only). The key is never logged and
never appears in output. No real key is stored in source or `.env.example`.

## 10. Data-quality principles

`assess_record_quality(entity)` produces a deterministic, explainable
`RecordQualityAssessment`: a 0–100 `data_quality_score`, a `completeness_ratio`,
and issue details. Dimensions: **completeness** (informational field population),
**validity** (e.g. country looks like a 2-letter code), **consistency**
(`updated_at ≥ created_at`), **uniqueness** (reflects ingestion's duplicate
finding — not re-derived). Score penalties: LOW −3, MEDIUM −10, HIGH −25.

We deliberately avoid inventing business rules — e.g. we never assume a PEP must
be sanctioned, or that an FATF-country customer is sanctioned.

## 11–12. Quality is not risk; match confidence is not risk

`data_quality_score` ≠ customer AML `risk_score` ≠ entity `match_confidence`.
A high-quality record can describe a high-risk customer; a low-quality record may
simply lack information. `RecordQualityAssessment` carries **no** risk or
confidence field (test-enforced).

## 13. Known limitations

- Representation boundaries only; **no access-control enforcement** yet (Phase 4).
- Person-vs-org detection is heuristic (`client_type == "Individual"`).
- Data-quality checks are intentionally minimal/deterministic; richer
  cross-field governance rules are future work.
- The extra source columns (OFAC/sectoral-sanctions/opacity) are not in the
  canonical contract, so they are not classified here yet.

## 14. Implemented now vs. planned

**Implemented (Phase 3):** deterministic field classification; masking;
keyed pseudonymization; context-based minimization; fail-closed unknown
context/field handling; log-safe & agent-safe representations; record-level
data-quality assessment; immutability of the canonical entity; JSON-safe output.

**Planned (later phases):** authentication/RBAC enforcement of who may request a
context; audit logging of representation access; retention/deletion policies;
encryption in transit/at rest; agent bounding/timeouts/kill-switch/audit;
classification of any future contract fields.

### Real-dataset check (aggregate, PII-safe)

2000 normalized entities → avg `data_quality_score` 100.0, avg
`completeness_ratio` 0.8 (dataset carries no aliases), 0 records with issues,
classification coverage 12/12. No raw customer records were printed.
