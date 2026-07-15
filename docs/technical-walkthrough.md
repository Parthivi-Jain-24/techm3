# Technical Walkthrough (Judge / Interviewer)

Each component below follows: **Problem → Security risk → Design decision →
Implementation → Testing → Limitation.** Technically accurate, no marketing
language. This is a *security-focused prototype* with a *production-oriented
architecture*; it is not production-certified.

---

## 1. Ingestion (CSV / XLSX / API)

- **Problem:** Bring untrusted KYC records in from files and external APIs.
- **Security risk:** Path traversal, malicious file types, formula injection,
  SSRF, memory exhaustion, PII leakage in logs.
- **Design decision:** One channel-agnostic core (`normalize_batch(header,
  rows, source)`); each channel is only a thin reader producing
  `(header, rows)` of strings. Files resolve inside an approved directory only.
- **Implementation:** `ingestion/connectors/kyc_file_connector.py`
  (`read_csv_rows`, `read_xlsx_rows` via openpyxl read-only+data-only — no
  formula evaluation; `read_kyc_rows` dispatch), `validators/file_validator.py`
  (extension + size + containment), `ingestion/api/` (SSRF-safe outbound
  client), `pipelines/kyc_ingestion_pipeline.py`.
- **Testing:** `test_ingestion.py`, `test_xlsx_ingestion.py`, `test_api_*.py`,
  E2E flows 1–3.
- **Limitation:** In-memory (no queue/DB); XLSX zip-bomb only partially
  mitigated (row cap + size limit); app-level SSRF only.

## 2. Schema validation & normalization

- **Problem:** Heterogeneous source columns must become one trustworthy shape.
- **Security risk:** Type confusion, silent duplicate "winners", accepting
  unexpected fields.
- **Design decision:** Explicit source→canonical mapping; strict Pydantic
  model with `extra="forbid"`; deterministic normalization; duplicates drop
  **all** occurrences (no silent winner).
- **Implementation:** `validators/kyc_schema_validator.py`, `mapping.py`,
  `schemas/kyc.py` (`NormalizedKYCEntity`), `reports.py` (`DataQualityReport`).
- **Testing:** `test_ingestion.py`, `test_data_quality.py`, `test_contracts.py`.
- **Limitation:** Canonical fields fixed to the challenge dataset; extra source
  columns are reported, not yet contract-promoted.

## 3. PII / privacy controls

- **Problem:** KYC records contain names, identifiers, sensitive flags.
- **Security risk:** PII in logs, over-exposure to downstream consumers.
- **Design decision:** Classification + deterministic masking + keyed
  pseudonymization + context-based minimization that **fails closed** on
  unknown contexts; the canonical entity excludes raw sensitive identifiers.
- **Implementation:** `privacy/classification/`, `privacy/masking/`
  (`masker.py`, `pseudonymize.py`), `privacy/minimization/`, `privacy/contexts.py`.
- **Testing:** `test_privacy_*.py`, `test_privacy_authz_integration.py`.
- **Limitation:** Rule-based classifier (not ML); pseudonymization dev-fallback
  key is non-secret and clearly labeled — a real key must come from the env in
  any non-local deployment.

## 4. OAuth2 / JWT authentication

- **Problem:** Identify callers without a heavyweight IdP for a hackathon.
- **Security risk:** Forged/`alg:none` tokens, privilege via token contents,
  password/token logging, account enumeration.
- **Design decision:** OAuth2 password flow issues short-lived HS256 JWTs with
  minimal claims; **authorization is never taken from the token** — the
  principal is re-resolved server-side each request; Argon2id password hashing;
  generic auth failures (no enumeration).
- **Implementation:** `api/routes/auth.py`, `identity/authentication/`
  (`tokens.py` explicit algorithm allow-list, `password.py`, `provider.py`,
  `dependencies.py`).
- **Testing:** `test_auth_api.py`, `test_auth_password_tokens.py`,
  `test_phase10_negative_security.py` (malformed/modified/expired/alg).
- **Limitation:** Local password flow + symmetric HS256; production wants
  OIDC/PKCE, asymmetric signing, refresh/revocation, MFA.

## 5. RBAC

- **Problem:** Not every authenticated caller may do everything.
- **Security risk:** Default-allow, scattered ad-hoc role checks, escalation.
- **Design decision:** Permission-based (never role-name checks in handlers);
  one central role→permission mapping; reusable `require_permission`
  dependency that **fails closed**; `service_account` grants nothing alone;
  automatic 401-vs-403 split.
- **Implementation:** `identity/rbac/mappings.py`, `identity/authorization/`
  (`permissions.py`, `policies.py`, `dependencies.py`).
- **Testing:** `test_rbac.py`, `test_api_route.py`, E2E flow 6; matrix in
  docs/rbac-matrix.md.
- **Limitation:** Coarse role set scoped to this workstream.

## 6. SSRF-safe API ingestion

- **Problem:** Pull KYC data from external HTTP APIs safely.
- **Security risk:** SSRF to internal/metadata endpoints, credential leakage,
  huge/hostile responses, redirect-based bypass.
- **Design decision:** Callers pick a **`source_id` only**; destinations are
  server-controlled and validated **before connecting** (HTTPS required;
  loopback/private/link-local/metadata/reserved/unspecified rejected for
  IPv4+IPv6; userinfo/fragment rejected); redirects off; explicit timeouts;
  streamed byte cap; credentials only in headers, never URLs/logs.
- **Implementation:** `ingestion/api/security.py`, `client.py`, `registry.py`,
  `models.py`.
- **Testing:** `test_api_security.py`, `test_phase10_negative_security.py`
  (localhost/private/metadata/userinfo/oversized/malformed).
- **Limitation:** App-level checks only — DNS-rebinding/TOCTOU residual;
  production needs network egress controls.

## 7. AES-256-GCM encryption at rest

- **Problem:** Protect sensitive application-generated artifacts on disk.
- **Security risk:** Wrong key size, nonce reuse, unauthenticated modes, key
  material in the envelope/logs, plaintext temp files.
- **Design decision:** Vetted `AESGCM` AEAD primitive; exactly 32-byte keys;
  fresh 96-bit `os.urandom` nonce **per operation**; AAD binds envelope
  metadata; versioned envelope carrying only a non-secret `key_id`; atomic
  writes; in-memory serialize→encrypt (no plaintext temp file).
- **Implementation:** `encryption/service.py`, `keys.py`, `models.py`,
  `artifact_store.py`.
- **Testing:** `test_encryption_*.py`, acceptance (key length, tamper),
  negative (wrong key, missing key).
- **Limitation:** Single active key per `key_id`; no automated rotation;
  encrypts an explicit artifact boundary, not "every byte on disk".

## 8. TLS 1.3 in transit

- **Problem:** Demonstrate encrypted transport with a strict modern profile.
- **Security risk:** Downgrade to TLS 1.0/1.1/1.2, committed private keys,
  false "TLS 1.3" claims, silent HTTP fallback.
- **Design decision:** A dedicated strict listener pinning
  `minimum_version = maximum_version = TLSv1_3`; self-signed **git-ignored**
  local dev cert; explicit separation of plain-HTTP dev vs. secure HTTPS demo;
  fail closed if cert/key missing.
- **Implementation:** `core/tls.py`, `deployment/run_https_dev.py`,
  `scripts/setup/generate-dev-tls-cert.ps1`.
- **Testing:** `test_tls_config.py`, `test_tls_headers_and_proxy.py`; **live
  handshake this phase negotiated TLSv1.3 and rejected TLS 1.2.**
- **Limitation:** Local demonstration listener only — not a production
  reverse proxy/ingress; no mTLS; no HSTS preload.

## 9. SecretProvider / Vault

- **Problem:** Resolve secrets (AES keys, API credentials) without hardcoding.
- **Security risk:** Silent fallback to a weaker source, token/secret logging,
  arbitrary Vault path access, audit-recursion.
- **Design decision:** One `SecretProvider` interface with two modes selected
  centrally; **fail-closed** vault mode (never falls back to env); one
  configured KV v2 path (no caller-supplied path); the Vault bootstrap token is
  read from the process env only and never logged; audit integration is
  one-directional so no secret→audit→secret loop.
- **Implementation:** `secrets/provider.py`, `factory.py`, `vault_provider.py`.
- **Testing:** `test_secrets_*.py`, `test_vault_provider.py`, E2E flows 4–5;
  **live Docker Vault smoke this phase** (real provider, no key/token leakage).
- **Limitation:** Token auth only; dev-mode Vault demonstrated (in-memory,
  HTTP); no secret-value caching or rotation engine.

## 10. Audit logging

- **Problem:** Record *who did what to which resource, when, with what
  outcome* — distinctly from ordinary diagnostic logs.
- **Security risk:** Logging bodies/headers/query strings/secrets/PII;
  unbounded metadata; tamper.
- **Design decision:** Canonical structured `AuditEvent`; plain-ASGI middleware
  that never reads the body and records only method + safe path + status;
  request-scoped `X-Request-ID` correlation; central `AuditService.emit` with
  **mandatory sanitization** (key redaction + depth/length/size bounds);
  dedicated append-only JSONL sink with an optional **SHA-256 hash chain** for
  tamper *evidence*; offline verifier.
- **Implementation:** `audit/events/`, `audit/middleware/`, `audit/service.py`,
  `audit/storage/`, `audit/verify.py`; integrations in auth/RBAC/ingestion/
  encryption/secrets.
- **Testing:** `test_audit_*.py`, `test_phase10_acceptance.py` (correlation,
  leakage), `test_phase10_negative_security.py`.
- **Limitation:** Tamper-**evident**, not tamper-proof — a hash chain does not
  stop whole-file deletion/truncate-and-refork; production must forward to
  append-only/WORM/SIEM storage.
