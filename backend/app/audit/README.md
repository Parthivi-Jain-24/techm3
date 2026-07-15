# Audit

**Owner:** Workstream 5, in coordination with Workstream 1

## Purpose

Maintain a complete, tamper-evident audit trail of user, agent, model, and system actions across the platform.

## Structure

- `events/` — audit event schema/definitions.
- `middleware/` — automatic capture of API-level actions (request/response metadata, actor identity).
- `storage/` — persistence layer for audit records.

## Inputs

Actions from every module: authentication events (`identity/`), ingestion events (`ingestion/`), screening results (`entity_intelligence/`), risk changes (`risk_intelligence/`), agent/investigation actions (`agents/`), and case/review decisions (`cases/`).

## Outputs

Immutable audit log entries consumed by `frontend/src/features/audit/` for the audit trail UI.

## Public Interface Expectations

Audit events must record actor type (user/agent/model/system), action, target entity, and timestamp at minimum. Never log raw PII or secrets — route sensitive fields through `backend/app/privacy/masking/` first.

## Security Considerations

- Audit records should be append-only; no module should update or delete existing audit entries.
- Access to raw audit logs is itself a permissioned action (`backend/app/identity/authorization/`).

## Integration Dependencies

- `backend/app/privacy/masking/` for safe logging.
- `backend/app/identity/` for actor identity.
