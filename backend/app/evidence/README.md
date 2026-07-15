# Evidence

**Owner:** Workstream 4 (Agent Orchestration, Autonomous Investigation, Evidence Grounding, Privacy Guardrails, SAR Drafting)

## Purpose

Maintain provenance and grounding for every claim made by risk scoring, investigations, and SAR drafts, so outputs are explainable and auditable.

## Structure

- `provenance/` — tracks the source of every piece of evidence (which ingestion record, which screening result).
- `grounding/` — links agent/model claims to specific evidence items.
- `validation/` — checks that generated content (e.g., SAR drafts) only references valid, existing evidence.

## Inputs

References from `entity_intelligence/`, `risk_intelligence/`, and `agents/`.

## Outputs

`evidence_ids` referenced throughout `Entity Intelligence Result`, `Risk Assessment`, and `Investigation Case` contracts.

## Public Interface Expectations

Every evidence item must be traceable back to a concrete source record — no evidence should be synthesized without provenance.

## Security Considerations

- Evidence records may reference sensitive source data — apply `backend/app/privacy/masking/` when evidence is displayed or exported.

## Integration Dependencies

- Consumed by `agents/sar_agent/` and `cases/review/` for human-reviewable evidence trails.
