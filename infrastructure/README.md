# Infrastructure

**Owner:** Workstream 1 for `database/`; shared for `docker/` and `monitoring/`.

## Structure

- `docker/` — Dockerfiles/compose fragments beyond the root `docker-compose.yml` (placeholder for now).
- `database/` — database provisioning, schema bootstrap, and migration-adjacent infra scripts (owned by Workstream 1).
- `monitoring/` — placeholders for observability config (logging, metrics, alerting) as the project matures.

No real credentials, connection strings, or production infrastructure definitions belong in this directory — see `SECURITY.md`.
