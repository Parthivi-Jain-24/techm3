# Cases

**Owner:** Workstream 5 (Frontend Dashboard, Human Review Workflow, Audit Trail UI, Case Management)

## Purpose

Manage the lifecycle of investigation cases and the human review workflow for high-impact decisions.

## Structure

- `services/` — case CRUD and lifecycle business logic.
- `workflows/` — state transitions (OPEN -> INVESTIGATING -> PENDING_REVIEW -> CLOSED).
- `review/` — human review/approval actions on agent-generated outputs (e.g., SAR drafts).

## Inputs

`Investigation Case` records from `agents/` (Workstream 4).

## Outputs

Case data and review decisions consumed by `frontend/` for the case management dashboard, and by `audit/` for the audit trail.

## Public Interface Expectations

Any change to a case's `status` must go through `workflows/`, not direct field mutation, so audit events are consistently emitted.

## Security Considerations

- Case-level authorization (who can view/act on which case) is enforced via `backend/app/identity/authorization/`.
- SAR submission and case closure require an explicit human reviewer action — never an automatic transition.

## Integration Dependencies

- `backend/app/agents/` for case creation.
- `backend/app/audit/` for logging every review action.
- `frontend/src/features/cases/` for the UI.
