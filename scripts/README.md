# Scripts

Utility scripts supporting local development. No business logic belongs here — call into `backend/app/` instead.

## Structure

- `setup/` — one-time environment setup scripts (venv, pre-commit hooks, local DB bootstrap).
- `data/` — scripts to generate/load synthetic sample data (never real data).
- `development/` — day-to-day dev convenience scripts (running services, seeding, resetting local DB).
