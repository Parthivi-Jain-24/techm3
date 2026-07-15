# Security Baseline (Workstreams A & B)

Mandatory security principles for my modules. Each item is tagged so nobody
mistakes intent for reality:

- **[P1]** — a control that is actually in place / true in Phase 1.
- **[PLANNED]** — an architectural commitment implemented in a later phase.

Phase 1 builds the *foundation and boundaries*, not the enforcement machinery.
Do not describe planned controls as if they already run.

## Principles

1. **No raw PII in application logs.** — **[P3, control available]** A log-safe
   representation exists (`app.privacy.to_log_safe_dict`) that omits names,
   aliases, and sensitive flags and pseudonymizes `client_id`; ingestion already
   logs only aggregates/masked ids. Enforcing its use everywhere is ongoing.
2. **No secrets in source code.** — **[P1]** Config reads from env / `.env`
   only; every setting has a safe non-secret default; `.env.example` holds
   placeholders only.
3. **No `.env` files committed.** — **[P1]** `.gitignore` ignores `.env` and
   `.env.*` while keeping `.env.example`.
4. **No unrestricted database access for future LLM agents.** — **[PLANNED]**
   (no DB and no agents exist in Phase 1).
5. **External content is untrusted input.** — **[P1, principle]** Documented as
   a hard boundary (see `docs/integration-contracts.md`,
   `docs/dataset-setup.md`); sanitization/extraction pipeline is **[PLANNED]**.
6. **Sensitive identifiers masked by default in user-facing output.** —
   **[P3]** Deterministic masking + keyed pseudonymization
   (`app.privacy.masking`) and context-based minimization
   (`app.privacy.minimize_kyc_entity`) implemented; `EXTERNAL_RESPONSE` /
   `AGENT_CONTEXT` are conservative and fail closed on unknown contexts. The
   `NormalizedKYCEntity` contract also **excludes** raw sensitive identifiers by
   design **[P1]**. (RBAC over who may request an un-masked context is Phase 4.)
7. **Encryption in transit and at rest.** — **at rest: [P6, partial]**
   AES-256-GCM (maintained `cryptography` AEAD primitive) implemented for
   **application-generated encrypted KYC export artifacts** under
   `data/encrypted/` only (`app.encryption`) — see docs/encryption-at-rest.md
   for the exact boundary. Keys are exactly 256-bit, resolved via the Phase 5
   `SecretProvider` boundary (never hardcoded), fresh random 96-bit nonce per
   operation, authenticated (tamper + wrong-key both fail closed, no partial
   plaintext). **Not** claimed: raw dataset encryption (unmodified fixture),
   database encryption (no database exists), disk/cloud-provider encryption.
   **In transit: [P7, local demonstration]** Strict TLS 1.3 listener
   (`deployment/run_https_dev.py`, `app.core.tls`) — `minimum_version =
   maximum_version = TLSv1_3` explicitly pinned; TLS 1.2 rejection and TLS 1.3
   success both live-verified (`openssl s_client`, `curl.exe`); self-signed
   local dev certificate only, never committed (git-ignored, verified empty
   `git ls-files certs/`). See docs/tls-in-transit.md for the exact scope. **Not**
   claimed: a production reverse proxy/ingress, HTTP→HTTPS redirect, mTLS, or
   that all network communication everywhere is TLS 1.3 — only this project's
   own local secure-demonstration listener is covered. Outbound Phase 5 HTTPS
   verification remains unchanged (`verify=False` absent — static test).
8. **Least privilege.** — **[P4]** Central role→permission mapping applies least
   privilege (`app.identity.rbac.mappings`); `SERVICE_ACCOUNT` grants nothing by
   itself, ADMIN is not blanket access. Still **[P1]** as a design rule for
   module boundaries.
9. **Short-lived authentication tokens.** — **[P4]** OAuth2-compatible token
   flow issues short-lived HS256 JWTs (default 15 min, validated > 0), Argon2id
   password hashing, RBAC with 401/403 and default-deny
   (`app.identity`, `docs/authentication-and-rbac.md`). Signing secret is
   environment-based (never committed). **[PLANNED]**: OIDC/PKCE, MFA, refresh
   /revocation, asymmetric signing — see that doc's hardening section.
10. **Every agent tool call authenticated, authorized, validated, bounded,
    audited.** — **[PLANNED]**.
11. **Every material AI-generated claim references evidence.** — **[PLANNED]**;
    the `EntityIntelligenceResult` contract already carries
    `evidence_references` to support this **[P1]**.
12. **High-impact actions require human approval.** — **[PLANNED]**.
13. **Human overrides require reasons and audit records.** — **[PLANNED]**.
14. **Retention and deletion policies.** — **[PLANNED]** (a `privacy/retention`
    module is reserved).
15. **Agent actions support timeouts, retry limits, rate limits, bounded tool
    access, and a kill switch.** — **[PLANNED]**.
16. **The LLM is not the sole source of truth.** — **[P1, principle]**
    Structured Pydantic contracts, not model output, define the data;
    `match_confidence` is a structured field, and evidence references are
    first-class. Enforcement (verified sources, policy-controlled agents) is
    **[PLANNED]**.

## Outbound request safety (API ingestion)

17. **No SSRF / open proxy in outbound API ingestion.** — **[P5]** Callers pick a
    `source_id` only (never a URL); destinations are validated before connecting
    (HTTPS required, userinfo/fragment/malformed rejected, loopback/private/
    link-local/metadata/multicast/unspecified IPs rejected for IPv4+IPv6), TLS
    verification never disabled, redirects off, timeouts + response-size caps
    enforced, secrets resolved via a `SecretProvider` and kept out of URLs/logs.
    App-level only — production still needs egress controls (see
    docs/api-ingestion.md §8). Audit events for ingestion runs are now
    implemented — see item 19.
18. **Secrets vault integration.** — **[P8, environment + vault modes]** The
    application implements a HashiCorp-Vault-backed `SecretProvider`
    (`app.secrets.vault_provider.VaultSecretProvider`, KV v2) for supported
    application secrets — the Phase 6 AES-256-GCM key and Phase 5
    API-ingestion credentials — with an environment-backed local-development
    mode (`SECRETS_PROVIDER=environment`, default) preserved unchanged.
    Provider selection is centralized (`app.secrets.factory`) and **fails
    closed**: vault mode never silently falls back to reading the environment
    (test-verified with an equivalent secret planted in both places
    simultaneously). Vault token is a bootstrap credential read directly from
    the process environment, never hardcoded, never logged, never a
    `pydantic-settings`/`.env` field. **Not** claimed: "all secrets are in
    Vault" (only the two integrated call sites are proven), "Vault is
    production-ready" (only dev-mode is demonstrated — in-memory, HTTP,
    single root token), or automated secret rotation (not implemented — see
    docs/secrets-vault.md §23-24).
19. **Security audit-logging middleware.** — **[P9]** A dedicated, structured
    audit subsystem (`app.audit`) — separate from ordinary application
    logs — records authentication, authorization, ingestion, encryption, and
    secret-access events as canonical `AuditEvent` records, correlated by a
    strictly-validated request ID (`X-Request-ID`), with centralized
    metadata sanitization (explicit sensitive-key redaction + bounded
    depth/length/collection size) enforced before any event is constructed.
    The request-correlation middleware is a plain ASGI middleware that never
    reads request or response bodies and never logs the raw query string,
    `Authorization` header, or cookies. The default local sink is a
    **tamper-evident** (SHA-256 hash-chained) JSON Lines file at
    `backend/var/audit/audit.jsonl` (git-ignored), with an offline
    verification tool (`python -m app.audit.verify`). **Not** claimed:
    "tamper-proof" or "immutable" (full-file deletion or a truncate-and-refork
    attack is not detectable from the file alone — see
    docs/audit-logging.md §25), a production SIEM/WORM destination (local
    file only), or that every possible security-relevant action is audited
    (a curated set of high-value events, not per-field/per-row logging — see
    docs/audit-logging.md §29 for the full limitations list).

## What Phase 1 actually enforces

- Secrets/`.env` kept out of git; app starts with no real credentials.
- Canonical contracts reject unexpected fields (`extra="forbid"`) and require
  non-blank identifiers and tz-aware timestamps.
- `match_confidence` (identity resolution) is structurally separate from
  customer risk — the result contract carries no risk field.
- Datasets and PII are kept out of git by `.gitignore`.
- Health endpoint is **truthful**: it reports process liveness only and claims
  no database, external, sanctions, or AI service health.
