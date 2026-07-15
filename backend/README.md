# Backend

FastAPI application for the Continuous KYC Autonomous Auditor.

## Structure

See `app/` for the module breakdown. Each domain module (`ingestion/`, `identity/`, `privacy/`, `entity_intelligence/`, `risk_intelligence/`, `agents/`, `evidence/`, `cases/`, `audit/`, `integrations/`) has its own README with ownership, inputs/outputs, and security notes.

## Setup (placeholder)

```bash
python -m venv .venv
source .venv/bin/activate   # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
cp ../.env.example ../.env  # then fill in local values
alembic upgrade head
uvicorn app.main:app --reload
```

## Testing

- `tests/unit/` — unit tests per module.
- `tests/integration/` — cross-module integration tests.
- `tests/security/` — auth, RBAC, PII masking, audit tests.
- `tests/fixtures/` — shared, synthetic test fixtures (no real data).
