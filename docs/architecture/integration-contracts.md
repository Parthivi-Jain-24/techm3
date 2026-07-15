# Integration Contracts

Because five developers work in parallel across separate branches, the interfaces between modules must be agreed upfront. This document defines placeholder JSON contracts for the data passed between workstreams. **These should eventually be implemented as Pydantic schemas** in the relevant `backend/app/*/schemas.py` (or `backend/app/schemas/`) files, and as matching TypeScript types in `frontend/src/types/`.

Changing a contract requires coordination with every workstream that consumes it — do not change field names/types unilaterally.

## Workstream 1 -> Workstream 2: Normalized KYC Entity

Produced by `backend/app/ingestion/`, consumed by `backend/app/entity_intelligence/`.

```json
{
  "client_id": "string",
  "client_type": "string",
  "display_name": "string",
  "country": "string",
  "sector": "string",
  "pep_flag": "boolean"
}
```

Do not include unnecessary raw sensitive identifiers (no SSNs, full account numbers, etc.) — apply data minimization before this record leaves Workstream 1.

## Workstream 2 -> Workstream 3 / Workstream 4: Entity Intelligence Result

Produced by `backend/app/entity_intelligence/`, consumed by `backend/app/risk_intelligence/` and `backend/app/agents/`.

```json
{
  "client_id": "string",
  "match_type": "SANCTIONS | OFAC | ADVERSE_MEDIA",
  "match_confidence": 0.0,
  "risk_signal": "string",
  "evidence_ids": ["string"],
  "source": "string",
  "detected_at": "ISO-8601 timestamp"
}
```

## Workstream 3 -> Workstream 4: Risk Assessment

Produced by `backend/app/risk_intelligence/`, consumed by `backend/app/agents/`.

```json
{
  "client_id": "string",
  "risk_score": 0,
  "risk_level": "LOW | MEDIUM | HIGH | CRITICAL",
  "confidence": 0.0,
  "risk_factors": [],
  "evidence_ids": [],
  "model_version": "string",
  "calculated_at": "ISO-8601 timestamp"
}
```

## Workstream 4 -> Workstream 5: Investigation Case

Produced by `backend/app/agents/`, consumed by `backend/app/cases/` and the frontend.

```json
{
  "case_id": "string",
  "client_id": "string",
  "status": "OPEN | INVESTIGATING | PENDING_REVIEW | CLOSED",
  "risk_score": 0,
  "confidence": 0.0,
  "summary": "string",
  "evidence_ids": [],
  "sar_draft_id": "string or null"
}
```

## Contract Change Process

1. Propose the change in the PR description or a design doc under `docs/architecture/`.
2. Tag reviewers from every consuming workstream (see [CODEOWNERS](../../.github/CODEOWNERS)).
3. Update this document alongside the schema change in the same PR.
4. Update both the Pydantic schema and any corresponding TypeScript type.

## Status

All contracts above are placeholders for the hackathon scaffold stage — no Pydantic implementations exist yet. Each owning workstream should implement its `schemas.py` referencing this document as the source of truth.
