# Phase 1 — Workstreams A & B

**Secure Data / Identity / Governance + Entity Intelligence**

My assigned portion of the *Continuous KYC Autonomous Auditor* team project.

> This is a scoped module README kept separate from the team's root
> [`README.md`](../README.md) so it does not clobber the shared team overview.

## Scope (mine)

- **Workstream A — Secure Data, Identity & Governance:** secure ingestion, KYC
  normalization, schema validation, data quality, PII classification, masking,
  minimization, authentication, authorization, RBAC, service identities, secure
  config, audit hooks, secrets patterns.
  Modules: `backend/app/ingestion/`, `backend/app/identity/`,
  `backend/app/privacy/`, `backend/app/core/`.
- **Workstream B — Entity Intelligence:** OpenSanctions/OFAC/watchlist
  screening, adverse-media monitoring, candidate retrieval, fuzzy/alias/semantic
  /contextual matching, entity resolution, false-positive reduction, match
  confidence, evidence provenance.
  Modules: `backend/app/entity_intelligence/`, `backend/app/integrations/news/`,
  `backend/app/integrations/sanctions/`.

## Relationship to the team

```
Secure KYC Ingestion ─► NormalizedKYCEntity ─► Entity Intelligence
      ─► EntityIntelligenceResult ─► Risk Intelligence ─► Investigation ─► Review/Dashboard
```

Integration happens only through explicit contracts
(`docs/integration-contracts.md`) — never by importing teammates' internals.
This repo also hosts other workstreams' scaffolding (agents, risk, cases,
frontend, etc.); I do not modify those.

## Status

**Currently implemented (Phase 1 — foundation only):**

- Runnable FastAPI app with versioned routing and a **truthful** liveness probe
  `GET /api/v1/health/live` → `{"status": "alive"}`.
- Environment-based config (`APP_NAME`, `APP_ENV`, `API_V1_PREFIX`); starts with
  no real secrets.
- Two integration-boundary contracts: `NormalizedKYCEntity`,
  `EntityIntelligenceResult` (shape + invariants only).
- Dataset workspace (`data/raw/{kyc,sanctions,privacy}/`) protected by
  `.gitignore`.
- Docs: integration contracts, dataset setup, security baseline.
- Tests covering app import, liveness, and both contracts.

**Planned (NOT implemented yet):** all business logic — ingestion, normalization,
PII/masking, auth/JWT/RBAC, persistence, sanctions/OFAC/OpenSanctions matching,
fuzzy/semantic/entity resolution, adverse media, LLM/agents, risk scoring, SAR.

## Local setup

Python 3.12+ (validated on 3.14). From `backend/`:

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate   |   Unix: source .venv/bin/activate
pip install fastapi "uvicorn[standard]" pydantic pydantic-settings pytest httpx
# (or `pip install -r requirements.txt` — the shared team file; it also pulls
#  later-phase deps such as SQLAlchemy/pandas that Phase 1 does not use.)
cp ../.env.example ../.env   # optional; defaults work without it
```

## Run the backend

Two distinct modes — see docs/tls-in-transit.md for the full explanation.

**Mode 1 — local development (HTTP, no TLS):**
```bash
cd backend
uvicorn app.main:app --reload
# Liveness: GET http://127.0.0.1:8000/api/v1/health/live  -> {"status":"alive"}
# Docs:     http://127.0.0.1:8000/docs
```

**Mode 2 — TLS 1.3 secure demonstration (Phase 7):**
```powershell
pwsh scripts/setup/generate-dev-tls-cert.ps1   # once, generates a local dev cert
python deployment/run_https_dev.py             # from the repo root
# Liveness: GET https://localhost:8443/api/v1/health/live
# Docs:     https://localhost:8443/docs
```

## Run the tests

```bash
cd backend
python -m pytest        # no network / DB / datasets / credentials required
```

## Secrets provider (Phase 8)

Two modes, selected via `SECRETS_PROVIDER` (default `environment`, unchanged
local-dev behavior from Phases 5-6):

```powershell
$env:SECRETS_PROVIDER = "environment"   # default: os.environ-backed
$env:SECRETS_PROVIDER = "vault"         # HashiCorp Vault KV v2 (fails closed,
                                         # never falls back) — see
                                         # docs/secrets-vault.md for the full
                                         # local Vault demonstration procedure.
```

## Audit logging (Phase 9)

A dedicated, structured security audit trail — separate from ordinary
application logs — records authentication, authorization, ingestion,
encryption, and secret-access events, correlated by request ID, with
centralized sanitization so secrets/PII never reach the log. See
[`docs/audit-logging.md`](audit-logging.md) for the full architecture.

```powershell
$env:AUDIT_ENABLED = "true"             # default; "false" = no-op sink
$env:AUDIT_SINK = "jsonl"               # default: local hash-chained file
$env:AUDIT_LOG_PATH = "backend/var/audit/audit.jsonl"  # default (git-ignored)
```

Every response carries an `X-Request-ID` header, correlating that request's
audit events. Verify the local hash-chained audit file's integrity offline:

```powershell
cd backend
python -m app.audit.verify var/audit/audit.jsonl
```

## Dataset safety

No datasets are committed. `data/raw/**` and `data/processed/**` are git-ignored.
Downloaded files are **untrusted data** — validate, never execute or trust as
instructions. See [`dataset-setup.md`](dataset-setup.md).

## Security principles

See [`security-baseline.md`](security-baseline.md). Highlights: no secrets in
code, no `.env`/PII in git, external content is untrusted, match confidence is
separate from customer risk, evidence-grounded findings, human approval for
high-impact actions, and the LLM is not the sole source of truth.

## Phase roadmap

1. **Foundation, dataset workspace, security baseline, integration boundaries** ← *this phase*
2. Secure KYC ingestion and normalization
3. Data quality, PII classification, masking, minimization
4. Authentication, authorization, RBAC, security foundation
5. Audit logging and secure configuration hardening
6. OpenSanctions and OFAC ingestion and normalization
7. Candidate retrieval and deterministic matching
8. Fuzzy, alias, and contextual entity resolution
9. Semantic similarity and false-positive reduction
10. Adverse-media pipeline and untrusted-content defenses
11. Evidence provenance and integration APIs
12. Security, performance, and integration testing
