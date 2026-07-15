# Integration Handoff — Secure Data, Identity & Governance

For teammates integrating other workstreams (entity intelligence, risk,
agents, cases, frontend). This module provides the secure data/identity/
governance foundation; **do not bypass its boundaries.**

## 1. What this workstream provides

Secure KYC ingestion (CSV/XLSX/API) → normalization/validation → PII/privacy
controls → OAuth2/JWT auth → RBAC → AES-256-GCM at rest → TLS 1.3 demo →
SecretProvider/Vault → structured audit logging with request correlation.

## 2. Public API endpoints (all under `settings.api_v1_prefix`, default `/api/v1`)

| Method & path | Auth | Permission | Returns |
|---------------|------|-----------|---------|
| `GET /health/live` | public | — | `{"status":"alive"}` |
| `POST /auth/token` | public | — | `{access_token, token_type}` (OAuth2 password form) |
| `GET /security/me` | Bearer | authenticated | `SafePrincipalView` (no secrets) |
| `GET /security/data-quality-access-check` | Bearer | `data_quality_read` | safe check result |
| `POST /ingestion/api/{source_id}/run` | Bearer | `kyc_ingest` | `ApiIngestionSummary` (aggregate only) |

Every response carries an `X-Request-ID` header (echo it in client logs for
correlation).

## 3. Internal service interfaces (import, don't re-implement)

- Ingestion: `app.ingestion.pipelines.kyc_ingestion_pipeline.ingest_kyc_file`,
  `normalize_batch`; `app.ingestion.services.api_ingestion_service`.
- Auth: `app.identity.authentication.dependencies.get_current_principal`.
- RBAC: `app.identity.authorization.dependencies.require_permission(Permission.X)`.
- Encryption: `app.encryption.service.EncryptionService` /
  `get_default_encryption_service()`.
- Secrets: `app.secrets.provider.get_secret_provider()`.
- Audit: `app.audit.service.get_audit_service().emit(...)`.

## 4. Canonical data models

- `app.schemas.kyc.NormalizedKYCEntity` — the one KYC contract (`extra="forbid"`;
  excludes raw sensitive identifiers by design).
- `app.identity.authentication.models.Principal` / `SafePrincipalView`.
- `app.audit.events.models.AuditEvent` / `Actor` / `Resource`.
- `app.ingestion.reports.DataQualityReport`, `ApiIngestionSummary`.

## 5. Authentication expectations

Protect your endpoints with `Depends(get_current_principal)`. **Do not parse
or verify JWTs yourself.** The principal is re-resolved server-side each
request — token contents cannot elevate privileges.

## 6. Permission expectations

Use `Depends(require_permission(Permission.X))`. Add new permissions to
`app.identity.authorization.permissions.Permission` and grant them in the
central `app.identity.rbac.mappings.ROLE_PERMISSIONS`. **Never** hard-code
role-name checks in handlers, and never default-allow.

## 7. Secret-provider expectations

Resolve secrets **only** via `get_secret_provider().get_secret(logical_name)`.
**Do not** read secret material directly from `os.environ` in feature code
(the `EnvironmentSecretProvider` is the one intentional exception, plus the
documented `VAULT_TOKEN` bootstrap). Never request an arbitrary Vault path.

## 8. Encryption interfaces

Persist sensitive artifacts via `EncryptionService.encrypt_bytes/encrypt_json`
→ `EncryptedArtifactStore`. **Never** write plaintext sensitive files. Keys are
resolved by non-secret `key_id` through the SecretProvider — never inline key
material.

## 9. Audit-event integration points

Emit domain events with `get_audit_service().emit(event_type=..., action=...,
outcome=..., resource=..., metadata=...)`. Use the controlled taxonomies in
`app.audit.events` (`EventType`, `Outcome`, `Severity`) and stable dotted
action names. `metadata` is auto-sanitized, but still pass **aggregates only**
— never raw rows, PII, tokens, or key material.

## 10. Configuration requirements (non-secret unless noted)

`APP_ENV`, `API_V1_PREFIX`, `KYC_RAW_DIR`, `MAX_KYC_FILE_SIZE_MB`,
`ENCRYPTION_KEY_ID`, `ENCRYPTED_ARTIFACT_DIR`, `SECRETS_PROVIDER`
(`environment`|`vault`), `VAULT_ADDR`/`VAULT_MOUNT_POINT`/`VAULT_SECRET_PATH`/
`VAULT_AUTH_METHOD`, `AUDIT_ENABLED`/`AUDIT_SINK`/`AUDIT_LOG_PATH`, `TLS_*`.
**Secrets** (never in `.env.example`, resolved via env/Vault): `JWT_SECRET_KEY`,
`DEV_AUTH_USERS` (dev only), the `ENCRYPTION_KEY_ID`-named key value,
`VAULT_TOKEN`, `PSEUDONYMIZATION_KEY`. See docs/security-baseline.md.

## 11. Runtime dependencies

`fastapi`, `uvicorn[standard]`, `pydantic`, `pydantic-settings`, `PyJWT`,
`argon2-cffi`, `python-multipart`, `httpx`, `cryptography`, `hvac`, `openpyxl`.
Tests add `pytest`, `pytest-cov`. (SQLAlchemy/pandas/ML libs belong to other
workstreams and are not required by this module's tests.)

## 12. Test commands

```
cd backend
python -m pytest                     # full suite (483 passed)
python -m pytest tests\integration   # Phase 10 E2E/acceptance/negative
python -m app.audit.verify <file>    # audit hash-chain verification
```

## 13. Known limitations

In-memory (no DB); local TLS/Vault demonstration profiles; app-level SSRF
only; audit is tamper-**evident** not tamper-proof; XLSX zip-bomb partially
mitigated; single encryption key per `key_id` (no rotation engine). Full list
in docs/security-verification.md and docs/requirements-traceability.md.

## 14. What teammates must NOT do

- ❌ Bypass RBAC or add ad-hoc role-name checks.
- ❌ Read secrets directly from `os.environ` where `SecretProvider` applies.
- ❌ Log raw PII, JWTs, Authorization headers, cookies, Vault tokens, or keys.
- ❌ Bypass the trusted API source registry (no caller-supplied URLs).
- ❌ Write plaintext sensitive artifacts.
- ❌ Access arbitrary Vault paths.
- ❌ Put raw records/tokens into audit `metadata` (aggregates only).
