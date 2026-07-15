# Requirements Traceability Matrix (Phase 10)

Workstream: **Secure Data, Identity, and Governance**. Every row is
evidence-based — a requirement is `PASS` only when actual behavior was
verified by an automated test and/or a live smoke test, not merely because a
file exists.

- **Environment:** Python 3.14.5, `backend/.venv`, Windows 11.
- **Standard test command:** `cd backend && python -m pytest`
- **Full suite result (this phase):** **483 passed, 0 failed, 0 skipped, 2 warnings** (~15s).
- Status legend: `PASS` / `PARTIAL` / `FAIL` / `N/A`.

| # | Requirement | Status | Implementation | Tests (representative) | Demo | Limitations |
|---|-------------|--------|----------------|------------------------|------|-------------|
| 1 | CSV ingestion | PASS | `ingestion/connectors/kyc_file_connector.py` `read_csv_rows`; `pipelines/kyc_ingestion_pipeline.py` `ingest_kyc_file`/`normalize_batch` | `test_ingestion.py` (19), `test_phase10_acceptance.py::test_e2e_csv_ingestion_authorized_then_pipeline` | demo-guide §CSV | in-memory, whole-file read (~2k rows) |
| 2 | XLSX ingestion | PASS | `read_xlsx_rows` (openpyxl read-only+data-only, no formula eval), `read_kyc_rows` dispatch | `test_xlsx_ingestion.py` (16), `test_phase10_acceptance.py::test_e2e_xlsx_ingestion_pipeline_safe` | demo-guide §XLSX | zip-bomb only partially mitigated (row cap + size limit); first sheet only |
| 3 | API ingestion | PASS | `ingestion/api/` (client, security, registry, models, extraction); `services/api_ingestion_service.py` | `test_api_pipeline.py`, `test_api_client.py`, `test_api_security.py`, `test_api_route.py` | demo-guide §API | in-memory; app-level SSRF only (see §8 of api-ingestion.md) |
| 4 | Schema validation | PASS | `validators/kyc_schema_validator.py`, `mapping.py`, `schemas/kyc.py` (`NormalizedKYCEntity`, `extra="forbid"`) | `test_ingestion.py`, `test_data_quality.py`, `test_contracts.py` | demo-guide §CSV | canonical fields fixed to the challenge dataset |
| 5 | PII validation/classification | PASS | `privacy/classification/` (classifier, models) | `test_privacy_classification.py` (5) | walkthrough §PII | rule-based classifier, not ML |
| 6 | Privacy masking | PASS | `privacy/masking/masker.py` | `test_privacy_masking.py` (12) | walkthrough §PII | — |
| 7 | Pseudonymization | PASS | `privacy/masking/pseudonymize.py` (HMAC keyed) | `test_privacy_masking.py` | walkthrough §PII | dev fallback key is non-secret & clearly labeled; real key via env in prod |
| 8 | Data minimization | PASS | `privacy/minimization/` (minimizer, policies), `privacy/contexts.py` | `test_privacy_minimization.py` (10), `test_privacy_authz_integration.py` | walkthrough §PII | fail-closed on unknown context |
| 9 | OAuth2-compatible auth | PASS | `api/routes/auth.py` (`OAuth2PasswordRequestForm`), `identity/authentication/` | `test_auth_api.py`, `test_auth_password_tokens.py` | demo-guide §Auth | local password flow only; OIDC/PKCE is future |
| 10 | JWT issuance | PASS | `identity/authentication/tokens.py` `create_access_token` (HS256, minimal claims) | `test_auth_password_tokens.py` | demo-guide §Auth | HS256 symmetric (documented) |
| 11 | JWT validation | PASS | `decode_access_token` (allow-list, signature+required claims) | `test_auth_password_tokens.py`, `test_phase10_negative_security.py` (malformed/modified/alg) | demo-guide §Auth | — |
| 12 | JWT expiry enforcement | PASS | `decode_access_token` `require exp`; `access_token_expire_minutes` (validated >0) | `test_phase10_acceptance.py::test_acceptance_jwt_expiry_enforced` | demo-guide §Auth | default 15 min |
| 13 | RBAC | PASS | `identity/authorization/` (dependencies, policies), `identity/rbac/mappings.py` | `test_rbac.py`, `test_api_route.py`, `test_phase10_acceptance.py` (allowed/denied) | demo-guide §RBAC + rbac-matrix.md | permission-based, central mapping |
| 14 | Default-deny authorization | PASS | `require_permission`/`require_permissions` fail closed; `SERVICE_ACCOUNT` grants nothing | `test_rbac.py::test_service_account_role_grants_nothing_by_itself`, `test_phase10_negative_security.py::test_neg_anonymous_denied_on_protected_endpoint` | demo-guide §RBAC | — |
| 15 | AES-256 at rest | PASS | `encryption/service.py` (AESGCM), `keys.py` (32-byte validation) | `test_encryption_service.py`, `test_encryption_keys.py`, `test_phase10_acceptance.py::test_acceptance_aes_key_length_enforced` | demo-guide §AES | opt-in export of app-generated artifacts only |
| 16 | AES-GCM tamper detection | PASS | authenticated AEAD + AAD binding; `InvalidTag`→`DecryptionFailedError` | `test_encryption_service.py`, `test_phase10_acceptance.py::test_acceptance_aes_tamper_detected`, `test_phase10_negative_security.py::test_neg_wrong_key_fails_closed` | demo-guide §AES | — |
| 17 | Encryption key resolution | PASS | `encryption/keys.py` `resolve_key` via `SecretProvider` | `test_encryption_keys.py`, `test_secrets_encryption_integration.py` | demo-guide §AES | — |
| 18 | TLS 1.3 in transit | PASS | `core/tls.py` (min=max=TLSv1_3), `deployment/run_https_dev.py` | `test_tls_config.py`, `test_tls_headers_and_proxy.py`; **live handshake** (see security-verification.md) | demo-guide §TLS | local self-signed demo listener only; not a prod ingress |
| 19 | SecretProvider abstraction | PASS | `secrets/provider.py` (`Protocol`), `factory.py` | `test_secrets_factory.py` | walkthrough §Secrets | — |
| 20 | Environment secret provider | PASS | `secrets/provider.py` `EnvironmentSecretProvider` | `test_secrets_environment_regression.py` | demo-guide §Vault | local-dev only |
| 21 | Vault secret provider | PASS | `secrets/vault_provider.py` (hvac, KV v2) | `test_vault_provider.py` (21); **live smoke** (Docker, this phase) | demo-guide §Vault | token auth only; dev-mode Vault |
| 22 | Vault fail-closed | PASS | `factory.py` no fallback; provider raises on unavailable/auth-fail | `test_secrets_factory.py::test_vault_mode_does_not_silently_fall_back_to_environment`, `test_phase10_acceptance.py::test_e2e_vault_fail_closed_no_environment_fallback` | demo-guide §Vault | — |
| 23 | Vault-backed AES key retrieval | PASS | same `EncryptionService`, provider swapped | `test_secrets_encryption_integration.py`, `test_phase10_acceptance.py::test_e2e_vault_backed_encryption_round_trip` | demo-guide §Vault | — |
| 24 | Vault-backed API credential retrieval | PASS | same `ApiConnector`, provider swapped | `test_secrets_api_integration.py` | demo-guide §API | — |
| 25 | Audit middleware | PASS | `audit/middleware/asgi.py` (plain ASGI) | `test_audit_middleware.py` (11) | demo-guide §Audit | — |
| 26 | Request correlation | PASS | `audit/middleware/request_id.py`, `context.py`; `X-Request-ID` | `test_audit_request_id.py`, `test_audit_middleware.py`, `test_phase10_acceptance.py::test_e2e_audit_correlation_shared_request_id` | demo-guide §Audit | — |
| 27 | Authentication auditing | PASS | `api/routes/auth.py`, `authentication/dependencies.py` | `test_audit_domain_integration.py` (auth), `test_phase10_acceptance.py` | demo-guide §Audit | no per-request success event on ordinary calls (by design) |
| 28 | Authorization auditing | PASS | `authorization/dependencies.py` | `test_audit_domain_integration.py`, `test_phase10_acceptance.py::test_e2e_authorization_denial_correlated_and_safe` | demo-guide §RBAC | allowed events fire on every check |
| 29 | Ingestion auditing | PASS | `pipelines/kyc_ingestion_pipeline.py`, `services/api_ingestion_service.py` | `test_audit_domain_integration.py`, `test_xlsx_ingestion.py` | demo-guide §Audit | aggregate metadata only |
| 30 | Encryption auditing | PASS | `encryption/service.py` | `test_audit_domain_integration.py` (enc/dec) | demo-guide §AES | — |
| 31 | Secret-access auditing | PASS | `audit/integrations.py` from `keys.py`/`client.py` | `test_audit_domain_integration.py`, `test_audit_leakage.py` | demo-guide §Vault | no recursion (AST-verified) |
| 32 | Audit sanitization | PASS | `audit/events/sanitize.py` (redaction + bounds) | `test_audit_sanitize.py` (15) | walkthrough §Audit | deliberate key allow/deny list |
| 33 | Audit integrity/tamper evidence | PASS | `audit/storage/jsonl.py` (SHA-256 chain), `audit/verify.py` | `test_audit_sink_jsonl.py` (15); **tamper smoke test** (this phase) | demo-guide §Audit-tamper | tamper-**evident**, not tamper-proof; full-file delete/truncate-refork undetectable |

## Summary

- **33 / 33 requirements: PASS.** No PARTIAL, no FAIL.
- XLSX ingestion (row 2) was the one deliverable found unimplemented at the
  start of Phase 10; it was implemented as the smallest correct fix (reusing
  the existing channel-agnostic pipeline) and is now fully tested. See
  security-verification.md and kyc-ingestion.md §3.
- All external integrations (Vault, outbound API) are **mocked in the
  automated suite** (no network/real-Vault dependency) and **additionally
  confirmed with live smoke tests** this phase (Docker Vault, TLS handshake).
