# Secure API Ingestion (Phase 5)

## 1. Scope

The third KYC ingestion channel (after CSV and XLSX): a secure **outbound** API
client that pulls structured KYC data from explicitly-configured trusted
sources, reusing the existing Phase 2 normalization and Phase 3 privacy controls.
No database, no entity intelligence, no encryption/TLS-deployment/vault/audit
middleware (those are later phases).

## 2. Inbound vs. outbound

- **Inbound**: a client calls us — `POST /api/v1/ingestion/api/{source_id}/run`
  (authenticated, RBAC-protected trigger).
- **Outbound**: our backend calls a trusted external API to retrieve data.

The connector is the outbound client; the endpoint only *triggers* it.

## 3–5. Trusted source model & why arbitrary URLs are prohibited

Callers select a **`source_id`** only. They can never supply a URL, credentials,
mapping, TLS, redirect, or timeout setting. `TrustedApiSourceConfig`
(`app/ingestion/api/models.py`) is a frozen, server-controlled model:

| Field | Purpose |
|---|---|
| `source_id` | caller-visible identifier |
| `base_url` + `endpoint_path` | server-controlled destination (never from caller) |
| `http_method` | `GET` (or `POST` for a trusted source); never caller-chosen |
| `auth_type` | `none` / `bearer_token` / `api_key_header` |
| `auth_secret_name` | **logical** secret name (never the value) |
| `auth_header_name` | header for `api_key_header` |
| `expected_content_type` | default `application/json` |
| `payload_location` + `data_field` | `root_list` or `data_field` |
| `field_mapping` | explicit source→canonical field map |
| `max_response_size_mb`, `follow_redirects`, `enabled` | safety knobs |
| `allow_insecure` | **test-only** flag (default False) |

An open URL fetcher would be an SSRF/proxy hazard — hence `source_id`-only.

## 4. Source registry

`ApiSourceRegistry.resolve(source_id)` returns the trusted config, rejecting
unknown (`UNKNOWN_SOURCE`) and disabled (`SOURCE_DISABLED`) sources. Built from
`API_SOURCES_JSON` (server config); empty by default.

## 6–7. SSRF threat model & defenses

Every destination is validated **before** any network call
(`app/ingestion/api/security.py`), using `urllib.parse` + `ipaddress`:

- HTTPS required (http only via the test-only `allow_insecure`).
- Reject URL **userinfo** (`user:pass@host`), **fragments**, malformed URLs.
- Reject `localhost` / known metadata hostnames.
- For literal IPs (no DNS) and for resolved hostnames, reject **loopback,
  private, link-local (incl. 169.254.169.254 metadata), multicast, unspecified,
  reserved** — IPv4 and IPv6.
- TLS verification is **never** disabled (`verify=False` appears nowhere);
  redirects are **off** by default.

## 8. DNS-rebinding limitation

Application-level host/IP checks reduce but do **not** eliminate SSRF: DNS
rebinding / TOCTOU between validation and connection remain possible. Production
must add **network egress controls, firewall rules, private networking, explicit
allowlists, and controlled DNS resolution**. We do not claim SSRF is impossible.

## 9. HTTPS requirement

External sources must use `https://`. (Deployment **TLS 1.3** enforcement for our
own service is a separate Phase 7 item — not done here.)

## 10–12. Authentication & secret boundary

Auth types: `NONE`, `BEARER_TOKEN`, `API_KEY_HEADER`. Secrets are referenced by
**logical name** and resolved through a `SecretProvider`
(`app/secrets/provider.py`): `EnvironmentSecretProvider` (default,
`SECRETS_PROVIDER=environment`) or `VaultSecretProvider`
(`SECRETS_PROVIDER=vault`, HashiCorp Vault KV v2 — **implemented in Phase 8**,
see docs/secrets-vault.md) behind the same interface. As designed, this
required **no changes to `ApiConnector`** — it only ever calls
`self._secrets.get_secret(source.auth_secret_name)`, where
`auth_secret_name` comes from server-controlled `TrustedApiSourceConfig`, so
callers still cannot choose a Vault path (proven in
`backend/tests/test_secrets_api_integration.py` with a synthetic API token
served by a fake Vault client). Secret values are placed only in request
**headers** — never in URLs/query strings — and are never logged or returned.

## 13. Timeouts

Explicit `httpx.Timeout(connect, read, write, pool)` from centralized settings
(`API_CONNECT_TIMEOUT_SECONDS`=5, `API_READ_TIMEOUT_SECONDS`=10, write=5, pool=5).
No infinite/default timeouts.

## 14. Redirects

`follow_redirects=False` by default. (If a trusted source ever opts in,
destinations must be re-validated and credentials not forwarded cross-host.)

## 15. Response-size limit

`MAX_API_RESPONSE_SIZE_MB`=10. Oversized `Content-Length` is rejected early, and
the **actual streamed bytes** are capped (so a missing/lying Content-Length can't
exhaust memory) → `RESPONSE_TOO_LARGE`.

## 16. Content-Type validation

Only `application/json` is accepted for a successful payload; `text/html`,
`application/octet-stream`, etc. are rejected (`INVALID_CONTENT_TYPE`). HTML is
never parsed as JSON.

## 17–18. Payload extraction & mapping

Two small typed shapes only — `ROOT_LIST` (`[ {...} ]`) or `DATA_FIELD`
(`{"data": [ {...} ]}`). **No JSONPath / expression engine.** Then an explicit,
server-controlled `field_mapping` renames source fields to canonical ones (values
coerced to strings so the shared normalizer treats them exactly like CSV input).

Example mapping: `{"customerId":"client_id","fullName":"client_name", ...}`.

## 19–20. Schema validation & PII/privacy reuse

API records go through the **same** Phase 2 `normalize_batch` (required fields,
lengths, boolean & sector-risk normalization, duplicate detection) and produce
the **existing** `NormalizedKYCEntity` — no competing model. Phase 3
classification/masking/minimization apply unchanged; the connector logs no
payloads or names.

## 21. Retry policy

Bounded: `API_MAX_RETRIES`=2 with exponential backoff, transient failures only
(timeouts, connection errors, `429`, `5xx`). **Never** retried: `4xx`
(incl. 401/403/404), malformed JSON, invalid content type, schema failures.
Retries are finite (max_retries + 1 attempts).

## 22. Duplicate handling

Within a batch, duplicate `client_id`s are detected and **all** occurrences
dropped (no silent winner). Durable cross-run exactly-once dedup requires
persistent storage / source versioning — a later integrated-system concern; no
fake persistence here.

## 23. RBAC for manual ingestion

`POST /api/v1/ingestion/api/{source_id}/run` requires JWT auth **and**
`require_permission(Permission.KYC_INGEST)` (the centralized Phase 4 dependency —
no ad-hoc role checks). Response is a safe aggregate summary only.

## 24. Safe errors

`ApiErrorCode` taxonomy (`UNKNOWN_SOURCE`, `UNSAFE_DESTINATION`,
`UPSTREAM_TIMEOUT`, `RESPONSE_TOO_LARGE`, `INVALID_CONTENT_TYPE`, `MALFORMED_JSON`,
`INVALID_PAYLOAD_SHAPE`, `SCHEMA_VALIDATION_FAILED`, …). Client-facing messages
never contain secrets, credentialed URLs, headers, upstream bodies, or stack
traces.

## 25. Audit integration (Phase 9 — implemented)

`ApiIngestionService.run` now emits `ingestion.api.started` /
`ingestion.api.completed` / `ingestion.api.failed` audit events (via
`app.audit`) with safe metadata (`source_id`, aggregate record/validation
counts, duration, a safe error category on failure) — never the upstream
payload, response body, or credentials. The actor is the authenticated
Principal from the triggering request where available. See
docs/audit-logging.md §13.

## 26. Current limitations

- Direct async request flow (no queue/worker) — fine for hackathon volume.
- In-memory only; no persistence/idempotency store.
- App-level SSRF checks only (see §8).
- Secret provider defaults to environment-backed; a HashiCorp Vault provider
  is available (`SECRETS_PROVIDER=vault`, Phase 8) but only dev-mode Vault has
  been demonstrated — see docs/secrets-vault.md.

## 27. Production-hardening requirements

Network egress allowlists + controlled DNS (SSRF depth); production Vault
deployment with workload-native auth instead of a static token (see
docs/secrets-vault.md §30); async job infrastructure for large ingestions;
per-source rate limiting; mTLS where applicable; forwarding the local audit
trail (Phase 9, implemented — see docs/audit-logging.md) to centralized
SIEM/WORM storage. TLS 1.3 for inbound traffic is implemented (Phase 7,
local demonstration profile — see docs/tls-in-transit.md).

## Testing

All tests use `httpx.MockTransport`, injected resolvers, and synthetic
sources/payloads — **no real network**. Run: `python -m pytest`.
