# Entity Intelligence

**Owner:** Workstream 2 (Entity Resolution, OpenSanctions, OFAC, Adverse Media Monitoring)

## Purpose

Screen corporate entities and related persons against sanctions and watchlists, resolve entities to reduce false positives, and monitor adverse media.

## Structure

- `sanctions/` — sanctions list screening logic.
- `ofac/` — OFAC-specific screening logic.
- `adverse_media/` — adverse media search and relevance scoring.
- `entity_resolution/` — matching/deduplication of entities across sources.
- `matching/` — shared fuzzy-matching / similarity utilities.

## Inputs

Normalized KYC Entity records from `ingestion/` (Workstream 1). See `docs/architecture/integration-contracts.md`.

## Outputs

`Entity Intelligence Result` records (match type, confidence, evidence references) consumed by `risk_intelligence/` (Workstream 3) and `agents/` (Workstream 4).

## Public Interface Expectations

Produce results conforming to the `Entity Intelligence Result` contract — do not leak raw third-party API response shapes downstream.

## Security Considerations

- Sanctions/OFAC/adverse-media API credentials are read from environment variables via `backend/app/integrations/`.
- Entity resolution must not fabricate confidence — unresolved/low-confidence matches should be flagged, not silently dropped.

## Integration Dependencies

- `backend/app/integrations/sanctions/`, `backend/app/integrations/news/` for external data access.
- `backend/app/evidence/` for evidence linkage (Workstream 4).
