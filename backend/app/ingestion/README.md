# Ingestion

**Owner:** Workstream 1 (Secure Data Ingestion, Authentication, Authorization, PII Protection, Database)

## Purpose

Securely ingest KYC profiles, AML transaction data, sanctions lists, OFAC data, adverse media feeds, and regulatory/privacy datasets from external sources into the platform's internal data model.

## Structure

- `connectors/` — source-specific ingestion connectors (file, API, batch feed).
- `validators/` — schema/data-quality validation before data enters the pipeline.
- `classifiers/` — sensitivity/PII classification of incoming fields.
- `pipelines/` — orchestration of connector -> validator -> classifier -> storage.
- `jobs/` — scheduled/triggered ingestion job definitions.

## Inputs

Raw KYC profiles, AML transaction records, sanctions/OFAC feeds, adverse media articles, regulatory datasets (from external sources or `data/raw/`, never committed to Git).

## Outputs

Normalized, validated, classified records written to the database via `backend/app/database/`. Downstream consumers: `entity_intelligence/` (Workstream 2), `risk_intelligence/` (Workstream 3).

## Public Interface Expectations

Ingestion pipelines should expose a stable internal contract (e.g., `NormalizedKycEntity`) rather than leaking raw source formats to downstream modules. See `docs/architecture/integration-contracts.md`.

## Security Considerations

- All ingested data must pass through PII classification before persistence.
- No raw source files (CSV/Excel/Parquet) may be committed to Git — see root `.gitignore`.
- Ingestion jobs run with least-privilege credentials scoped to their specific source.

## Integration Dependencies

- `backend/app/privacy/classification/` for sensitivity tagging.
- `backend/app/database/` for persistence.
- `backend/app/audit/` for logging ingestion events.
