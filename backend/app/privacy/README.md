# Privacy

**Owner:** Workstream 1 (core PII controls) — other workstreams consume these utilities rather than reimplementing them.

## Purpose

Protect PII and sensitive banking data across the platform through masking, classification, data minimization, and retention controls.

## Structure

- `masking/` — field-level masking/redaction utilities for logs, UI, and exports.
- `classification/` — sensitivity classification of data fields (PII, financial, public).
- `minimization/` — helpers to strip cross-module payloads down to required fields only.
- `retention/` — data retention/expiry policy enforcement.

## Inputs

Raw records from `ingestion/`, structured payloads from any module that needs to log, display, or transmit potentially sensitive data.

## Outputs

Masked/redacted values, classification labels, minimized payloads safe for cross-module transmission or logging.

## Public Interface Expectations

Any module writing to `backend/app/audit/` or exposing data via `backend/app/api/` must route sensitive fields through `masking/` first.

## Security Considerations

- This module is the single source of truth for "what counts as sensitive" — do not duplicate classification logic elsewhere.
- Masking failures should fail closed (mask/deny by default), not fail open.

## Integration Dependencies

- Used by `ingestion/`, `audit/`, `cases/`, `agents/`, and the API layer.
