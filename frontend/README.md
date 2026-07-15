# Frontend

**Owner:** Workstream 5 (Frontend Dashboard, Human Review Workflow, Audit Trail UI, Case Management)

## Purpose

React + TypeScript + Tailwind CSS dashboard for case management, human review of agent-generated outputs (risk assessments, SAR drafts), and the audit trail.

## Structure

- `src/app/` — app shell, routing, providers.
- `src/components/` — shared, reusable UI components.
- `src/pages/` — top-level route pages.
- `src/features/` — feature-scoped modules:
  - `dashboard/` — overview/landing dashboard.
  - `cases/` — case list/detail, maps to `backend/app/cases/`.
  - `customers/` — customer/entity profile views.
  - `investigations/` — investigation timeline/status views.
  - `risk/` — risk score and risk timeline visualizations.
  - `sar/` — SAR draft review UI.
  - `audit/` — audit trail UI, maps to `backend/app/audit/`.
  - `security/` — login, session, permission-aware UI elements.
- `src/services/` — API client layer.
- `src/hooks/` — shared React hooks.
- `src/types/` — shared TypeScript types (mirroring backend contracts in `docs/architecture/integration-contracts.md`).
- `src/utils/` — shared utilities.

## Setup (placeholder)

```bash
npm install
npm run dev
```

## Security Considerations

- Never store JWTs or sensitive tokens in `localStorage` without a documented threat-model decision — prefer httpOnly cookies where feasible.
- All PII displayed in the UI must already be masked/minimized by the backend — the frontend should not perform its own unmasking.
- High-impact actions (SAR approval, case closure) must go through explicit confirmation UI wired to `backend/app/cases/review/`.
