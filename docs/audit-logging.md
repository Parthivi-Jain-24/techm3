# Security Audit-Logging Middleware (Phase 9)

## 1. Scope

A dedicated security audit-logging subsystem (`backend/app/audit/`) and a
request-correlation middleware, recording security- and governance-relevant
actions — authentication, authorization, ingestion, encryption, secret
access, and HTTP request completion — as structured, sanitized, correlated
events, without leaking secrets or raw PII. This is a **new, separate**
subsystem: no existing Phase 1–8 logging was renamed or replaced.

## 2. Audit logs vs. application logs

| | Application logs (`app.core.logging`) | Audit logs (`app.audit`) |
|---|---|---|
| Answers | What error occurred? Which component failed? What's useful for debugging? | Who attempted what security-relevant action, on what, when, from which request, with what outcome? |
| Format | Free-text / diagnostic | Structured `AuditEvent` records, one per line |
| Destination | Standard logging (not built out beyond a placeholder in Phase 1–8) | Dedicated sink (`backend/var/audit/audit.jsonl` by default) |
| Content policy | May include stack traces in safely-configured diagnostics | Never a raw exception dump — only safe error *categories* |

`app/core/logging.py` remains an unused placeholder — Phase 9 did not build
out general application logging; only the audit subsystem.

## 3. Architecture

```
Request
  -> AuditContextMiddleware (plain ASGI; request-ID + anonymous context)
  -> Phase 4 authentication (enriches context with a safe actor)
  -> Phase 4 authorization / RBAC (emits ALLOWED/DENIED)
  -> Business operation (ingestion / encryption / secret access — emits its
     own explicit domain event)
  -> AuditService.emit() (sanitizes metadata, builds AuditEvent)
  -> AuditSink.write() (HashChainedJsonLinesAuditSink by default)
  <- request.completed event emitted as the middleware unwinds
```

Package layout:

```
app/audit/
  events/    AuditEvent, Actor, Resource, enums, sanitize.py, actions.py, resources.py
  storage/   AuditSink protocol, InMemoryAuditSink, NullAuditSink,
             HashChainedJsonLinesAuditSink, paths.py, hashchain.py
  middleware/ AuditContextMiddleware (plain ASGI), request_id.py, context.py
  service.py  AuditService — the single choke point every event passes through
  integrations.py  shared secret-access-audit helper
  verify.py   offline hash-chain verification CLI
```

## 4. Canonical `AuditEvent` schema

`app/audit/events/models.py`:

```python
class AuditEvent(BaseModel):
    event_id: str                  # UUID4, auto-generated
    timestamp: datetime            # tz-aware UTC, auto-generated
    event_type: EventType          # controlled enum
    action: str                    # validated "domain.operation" format
    outcome: Outcome                # controlled enum
    severity: Severity = INFO       # controlled enum
    request_id: str | None
    actor: Actor = ANONYMOUS_ACTOR
    resource: Resource | None
    source: str = "backend"
    duration_ms: float | None       # >= 0
    metadata: dict[str, Any]        # always sanitized before construction
```

`extra="forbid"` on every model — an unrecognized field is a construction
error, not silently accepted. Every event is built exclusively through
`AuditService.emit()`; nothing else in the codebase constructs an
`AuditEvent` or writes to a sink directly.

## 5. Event taxonomy

`EventType` (`app/audit/events/enums.py`): `HTTP_REQUEST`, `AUTHENTICATION`,
`AUTHORIZATION`, `INGESTION`, `DATA_VALIDATION`, `PII_PROCESSING`,
`ENCRYPTION`, `SECRET_ACCESS`, `SECURITY_CONFIGURATION` (`DATA_VALIDATION`
and `PII_PROCESSING` and `SECURITY_CONFIGURATION` are reserved — no current
call site emits them; aggregate PII-processing signal already rides on the
`INGESTION` events, see §12).

`Outcome`: `SUCCESS`, `FAILURE`, `DENIED`, `ERROR`. `Severity`: `INFO`,
`WARNING`, `ERROR`, `CRITICAL` (nothing is classified `CRITICAL` in this
phase — reserved for a future genuinely critical signal, e.g. repeated
authentication failures from one actor).

`action` is a validated, curated string (`app/audit/events/actions.py`),
e.g. `authentication.succeeded`, `ingestion.file.completed`,
`secret.access.failed` — never derived from user input; the model rejects
any value not matching `domain.operation[.suboperation]` lowercase format.

## 6. Actor model

```python
class Actor(BaseModel):
    actor_id: str
    actor_type: ActorType   # ANONYMOUS | USER | SERVICE | SYSTEM
    roles: tuple[str, ...]
```

`actor_id` is always the Phase 4 `Principal.principal_id` — a stable
internal identifier (e.g. `U-ANALYST`), never a password, JWT, or full
profile. The demo identities in this repo already use opaque IDs rather than
emails, so no redesign was needed (`Principal` structurally has no field for
a credential at all — see `app/identity/authentication/models.py`).

- `ANONYMOUS_ACTOR` (`actor_id="anonymous"`): the default for an HTTP
  request before authentication runs, or a request that never authenticates.
- `SYSTEM_ACTOR` (`actor_id="system"`): the default OUTSIDE any HTTP request
  (CLI ingestion jobs, startup code) — deliberately distinct from anonymous,
  which specifically means "an HTTP request arrived with no valid
  credentials."
- A real `USER`/`SERVICE` actor appears only after Phase 4 authentication
  succeeds, via `actor_from_principal()`.

## 7. Resource model

```python
class Resource(BaseModel):
    resource_type: str   # snake_case, e.g. "secret_reference"
    resource_id: str | None
```

Used resource types (`app/audit/events/resources.py`): `api_endpoint`,
`ingestion_source`, `encrypted_artifact`, `secret_reference`, `permission`.
`resource_id` is always a pre-vetted safe value: a route path (never a query
string), a file **basename** (never an absolute path or raw content), a
`source_id`/`key_id`/logical secret name (all already treated as non-secret
metadata by Phases 5/6/8), or a `Permission` value — never a raw record,
credential, or key material.

## 8. Request ID / correlation

`app/audit/middleware/request_id.py`. An incoming `X-Request-ID` is accepted
**only** if it is a well-formed UUID ≤ 64 characters; anything else
(missing, malformed, overlong, containing control/newline characters) is
replaced with a freshly generated UUID4 — there is no way to inject
arbitrary or unbounded text into a value that ends up in structured output.
The resolved ID is returned as `X-Request-ID` on every response and is the
same value used for every audit event emitted during that request (request
completion, authentication, authorization, domain events).

## 9. Middleware behavior

`AuditContextMiddleware` (`app/audit/middleware/asgi.py`) is a **plain ASGI
middleware** — `async def __call__(self, scope, receive, send)` — not a
`starlette.middleware.base.BaseHTTPMiddleware` subclass. Two reasons:

1. **Body/streaming safety**: it never touches `receive` or reconstructs the
   response body. It only reads `scope` (method, path, headers) before the
   call and the `http.response.start` message's status code after. Request
   and response bodies pass through completely untouched — there is no
   `await request.body()` anywhere in this subsystem, and streaming
   responses are never buffered.
2. **Context propagation**: the downstream app runs in the exact same
   coroutine/task as the middleware (`await self.app(...)`), so a
   `contextvars` value set here (`app/audit/middleware/context.py`) is
   reliably visible to every dependency, route handler, and internal
   service call for that request — including code with no access to the
   `Request` object at all (encryption, secret resolution).

At request entry it resolves/generates the request ID, creates an
`AuditContext(request_id, actor=ANONYMOUS_ACTOR)`, and stores it in a
contextvar. As the request unwinds (in a `finally` block, so it fires even
on an unhandled exception) it emits one `request.completed` event with:
method, a **safe path** (§10), the response status code, outcome
(`SUCCESS`/`FAILURE`/`DENIED`/`ERROR` by status-code bucket), severity, and
duration in milliseconds.

Order in `app/main.py`: `SecurityHeadersMiddleware` is added first,
`AuditContextMiddleware` second — Starlette wraps the most-recently-added
middleware outermost, so `AuditContextMiddleware` wraps everything else,
guaranteeing its context is set before any downstream code (including
security headers, routing, auth) runs.

## 10. Safe route/path resolution — a documented limitation

Ideally the audit event would record the matched route **template** (e.g.
`/api/v1/ingestion/api/{source_id}/run`) rather than the concrete path. In
practice, this FastAPI version wraps included sub-routers in an internal
`_IncludedRouter` object that does not eagerly flatten path prefixes onto
each route; by the time the outer middleware can read `scope["route"]`, its
`.path` attribute resolves to only the **leaf-relative** fragment (e.g.
`"/live"` instead of `"/api/v1/health/live"`) — version-fragile and less
useful than intended. Rather than reconstruct or invent a template, the
middleware uses `scope["path"]`: the concrete, full request path, which ASGI
**guarantees never includes the query string**. Any path *parameter values*
this reveals (e.g. a literal `source_id`) are not treated as sensitive
elsewhere in this design either — `source_id` is already used directly as an
`ingestion_source` resource_id (§12) — so this is not a new leak, just a
less-templated one. `?...` query strings are never read or logged under any
circumstance.

## 11. Authentication events

Integrated at two points in the **unchanged** Phase 4 flow:

- **`POST /api/v1/auth/token`** (`app/api/routes/auth.py`): the actual
  password-authentication attempt. Emits `authentication.succeeded`
  (`actor` = the resolved Principal, `metadata={"mechanism": "password"}`)
  or `authentication.failed` (`outcome=FAILURE`, **anonymous actor** —
  deliberately no attempted username is logged, preserving the same
  no-account-enumeration guarantee this endpoint already gives HTTP callers;
  a wrong-password attempt and an unknown-username attempt produce
  identically-shaped audit events).
- **`get_current_principal`** (`app/identity/authentication/dependencies.py`,
  the per-request Bearer-token check used by every protected endpoint): a
  **presented-but-rejected** token (invalid/expired/unknown/inactive
  principal) emits `authentication.failed` with a safe `reason` code
  (`INVALID_TOKEN`, `UNKNOWN_OR_INACTIVE_PRINCIPAL`,
  `AUTHENTICATION_NOT_CONFIGURED`). A **missing** token is NOT audited here
  — that's simply an unauthenticated request, already visible as a 401 in
  the `request.completed` event, not a rejected credential. A **successful**
  Bearer check does not emit its own event either — it only enriches the
  request's audit context (`set_actor`) so later authorization/domain
  events and the final `request.completed` event attribute correctly; a
  separate event on every single authenticated API call would duplicate the
  one already emitted at login and add volume with no new signal (see §29).

Never logged: password, password hash, the JWT itself, the `Authorization`
header, or token claims.

## 12. Authorization events

`require_permission()` / `require_permissions()`
(`app/identity/authorization/dependencies.py`) — the **same, unmodified**
centralized RBAC dependency — emits `authorization.allowed` or
`authorization.denied` right where it makes the decision. The audit call
never re-derives or duplicates the decision; it only records what
`has_permission()` (Phase 4, untouched) already decided. `resource` is the
required `Permission` value (e.g. `kyc_ingest`); `actor` is the safe
Principal-derived actor. Never logged: the JWT, or a full `Principal` dump.

## 13. Ingestion events

**File ingestion** (`ingest_kyc_file()`,
`app/ingestion/pipelines/kyc_ingestion_pipeline.py` — CSV and XLSX, via the
channel-agnostic `read_kyc_rows` dispatch; the audit `metadata.source_format`
records which, see docs/kyc-ingestion.md): emits `ingestion.file.started` /
`ingestion.file.completed` / `ingestion.file.failed`. Resource ID is the
**basename only** (never the caller-supplied string verbatim, which could
contain traversal segments, and never an absolute path). Metadata is
aggregate-only: total/valid/invalid row counts, duplicate count, validation
issue count, duration — never a raw row, a full `NormalizedKYCEntity`, or
any PII value.

**API ingestion** (`ApiIngestionService.run()`,
`app/ingestion/services/api_ingestion_service.py` — this file's docstring
already anticipated this exact integration point since Phase 5): emits
`ingestion.api.started` / `.completed` / `.failed`. Resource ID is the
server-configured `source_id`. Metadata is the same aggregate-count shape —
never the upstream payload, response body, or credentials.

## 14. Encryption events

`EncryptionService.encrypt_bytes` / `decrypt_bytes`
(`app/encryption/service.py`) emit `encryption.encrypt.succeeded/failed` and
`encryption.decrypt.succeeded/failed`. Metadata: `algorithm`
(`"AES-256-GCM"`), `artifact_type`, and (on failure) a safe error
**category** (the exception class name, e.g. `DecryptionFailedError` —
never `str(exc)` or a stack trace). `resource_id` is the `key_id` — Phase 6
already treats this as non-secret envelope metadata. Never logged: key
material, plaintext, ciphertext, nonce, authentication tag, or the full
envelope.

## 15. Secret-access events

A small shared helper, `audit_secret_access()`
(`app/audit/integrations.py`), is called from the two existing places a
logical secret is actually resolved:
`app/encryption/keys.py::resolve_key()` (encryption key retrieval) and
`app/ingestion/api/client.py::ApiConnector._auth_headers()` (API credential
retrieval) — **not** inside `app.secrets.factory.resolve_secret_provider()`
itself, because wrapping the returned provider object there would break
Phase 8's existing `isinstance(provider, VaultSecretProvider)` tests. Emits
`secret.access.succeeded` / `secret.access.failed` with `resource_id` = the
logical secret name (non-secret by the Phase 5/6/8 design already) and
`metadata={"provider_type": "EnvironmentSecretProvider" | "VaultSecretProvider"}`.
The secret **value** never passes through this helper at all — it isn't
even a parameter.

**No audit recursion**: `app/audit/service.py`, `.../storage/jsonl.py`, and
`.../storage/memory.py` contain zero imports of `app.secrets` (verified by a
static AST-import test, `test_audit_domain_integration.py`) — the local
sink never needs to resolve a secret to write an event, so there is no path
by which "audit a secret access" could itself trigger another secret
access.

## 16. Never-log data (hard boundary)

Never appears in an audit event, anywhere: passwords, password hashes, raw
JWTs, refresh tokens, `Authorization` headers, cookies, Vault tokens, Vault
responses, secret values, API credentials, AES key material, private TLS
keys, raw KYC payloads, raw spreadsheet rows, full request/response bodies,
full `Principal` objects, or arbitrary exception dumps/stack traces.
Verified by the leakage test suite (§27) using synthetic markers.

## 17. Centralized sanitization

`app/audit/events/sanitize.py::sanitize_metadata()` runs inside
`AuditService.emit()` for **every** event — call sites cannot bypass it. Two
controls:

1. **Key-name redaction**: an explicit substring list (`password`, `secret_value`,
   `client_secret`, `token`, `authorization`, `api_key`, `encryption_key`,
   `private_key`, `vault_token`, `credential`, `cookie`, …) checked against
   each metadata key, case-insensitively. A deliberate **allow-list**
   (`key_id`, `secret_id`, `secret_reference`, `source_id`, `artifact_type`,
   `provider_type`, `permission`, `algorithm`, …) is checked *first*, so
   non-secret identifiers that happen to contain a substring like "secret"
   (e.g. `secret_reference`) are never redacted — the sanitizer never
   matches on the bare word "key" alone.
2. **Structural bounds**: max metadata depth (4), max string length (512,
   truncated with a `...[TRUNCATED]` suffix), max collection size (20
   items) and max dict keys (30) per level. An unserializable object (an
   exception, a custom class instance) is never `str()`'d or `repr()`'d —
   it degrades to a `[UNSERIALIZABLE:<TypeName>]` marker so a value's
   `__repr__` can never become an accidental leak path.

`sanitize_metadata()` itself never raises — any input it cannot handle
degrades to a safe placeholder rather than breaking the caller's real
operation.

## 18. JSONL sink

`HashChainedJsonLinesAuditSink` (`app/audit/storage/jsonl.py`): one JSON
object per line (never pretty-printed), UTF-8, append-only. A per-process
`threading.Lock` serializes writes so the write and the in-memory
`previous_hash` pointer never diverge within one process (does **not**
protect against multiple separate OS processes writing to the same file
concurrently — out of scope for a local demonstration sink).

## 19. Audit file location

`backend/var/audit/audit.jsonl` by default (`AUDIT_LOG_PATH`, resolved
relative to the repo root). `app/audit/storage/paths.py::resolve_audit_log_path()`
is the **only** place the configured path is interpreted: it confirms the
resolved path stays inside the approved `backend/var/audit/` directory and
silently falls back to the approved default if a misconfiguration (e.g. a
`..` traversal) would place it elsewhere. There is no code path anywhere in
this subsystem that accepts a path or path fragment from an HTTP caller.

## 20. Git-ignore behavior

`.gitignore` excludes `backend/var/audit/**` (re-including the directory
structure and a `.gitkeep`, mirroring the existing `data/encrypted/**`
pattern) so the runtime audit trail is never committed — verified by a test
that writes a probe file and confirms `git status --ignored` reports it as
ignored (`test_audit_sink_jsonl.py`, mirroring the existing
`test_no_real_private_key_committed` pattern from Phase 7).

## 21. Sink failure policy

Both event **construction** and sink **write** failures inside
`AuditService.emit()` are caught, reported through the ordinary application
logger (`logging.getLogger("app.audit")` — never the audit sink itself, so
there is no risk of recursing into a failed sink), and swallowed — the
caller's real operation (an ingestion run, an encryption call, the HTTP
request) always proceeds unaffected. A local demo audit file being
temporarily unavailable must not become a denial-of-service vector for the
actual KYC/security operations. If the configured sink itself cannot be
constructed at all (invalid `AUDIT_SINK` value, unwritable directory), the
audit subsystem logs a warning and falls back to a `NullAuditSink` for the
process rather than blocking application startup or any request. This is a
deliberate choice, not an oversight: fail-**closed** auditing (block the
operation if audit can't be recorded) was considered and rejected for this
hackathon phase as disproportionate risk for a local demonstration sink; a
future production deployment could make this configurable per the note in
§30.

## 22. Client-IP trust limitations

No client-IP field is recorded in any audit event in this phase. Phase 7
established that `X-Forwarded-For` is untrustworthy unless the request came
through an explicitly configured trusted proxy (`TRUSTED_PROXY_IPS`, empty
by default = trust none). Rather than record framework-resolved
`request.client.host` (which is `None`/unreliable in this deployment shape)
or blindly trust a spoofable header, Phase 9 omits client IP entirely —
recording attacker-controlled data as if it were authoritative would be
worse than omitting it. A future iteration could add it only when
`request.client.host` is populated by a genuinely trusted layer.

## 23. Phase 7 proxy interaction

`AuditContextMiddleware` does not read or trust any `X-Forwarded-*` header
for anything — it only reads `X-Request-ID` (validated, §8) and the ASGI
`scope["method"]`/`scope["path"]`, both of which are set by the ASGI server
itself, not attacker-influenced headers. There is no interaction with, or
dependency on, the Phase 7 `trusted_proxy_ips` mechanism (that setting is
consumed by Uvicorn's `forwarded_allow_ips`, upstream of this middleware).

## 24. Hash-chain behavior (implemented)

Each written line carries two extra fields beyond the `AuditEvent` payload:

- `previous_hash`: the prior line's `event_hash`, or a documented genesis
  value (`"0" * 64`) for the first line in a file.
- `event_hash`: `SHA-256` over the **canonical JSON encoding** (sorted keys,
  no extra whitespace — `app/audit/storage/hashchain.py::canonical_json()`)
  of the event **including** `previous_hash` but **excluding** `event_hash`
  itself.

No custom cryptographic signatures and no HMAC/signing secret are used —
only `hashlib.sha256` over a deterministic encoding, exactly as scoped by
the phase's constraints. The write-time hashing (`storage/jsonl.py`) and the
verify-time hashing (`verify.py`) share the same `hashchain.py` primitives
so they cannot drift apart.

## 25. Tamper-evidence limitations

**This chain provides tamper *evidence*, not tamper *proof* or
immutability.** Specifically, it:

- **Detects** a modified line, a reordered/inserted line, or a broken
  `previous_hash` link anywhere in the file (verified by dedicated tests).
- **Does NOT prevent** someone with filesystem access from deleting the
  entire file, or truncating the tail and re-chaining a fabricated
  continuation from that truncation point forward (the "confirmed by the
  file" claim only extends to the actual file being verified — it can't
  prove nothing was ever removed from *before* the earliest line still
  present).
- **Does NOT provide non-repudiation** — there is no signing key, so an
  attacker with write access to the file *could* rewrite it entirely with a
  fresh internally-consistent chain. Verification proves internal
  self-consistency, not that the content is what the application actually
  wrote.
- **Does NOT replace** protected, centralized, access-controlled, WORM
  production storage (§30).

This document, `docs/security-baseline.md`, and all code comments
deliberately say **"tamper-evident"**, never "tamper-proof" or "immutable."

## 26. Audit-chain verification

```
cd backend
python -m app.audit.verify <path-to-audit.jsonl>
```

Reports `VALID chain: N event(s) verified` (exit code 0) or
`INVALID chain: failure detected at line N (... reason)` (exit code 1).
Requires no secret, network access, database, or Vault — pure local
SHA-256 hashing over the file. **Never prints event content** (actor IDs,
resource IDs, metadata) — only line numbers and a safe structural failure
category (`malformed JSON line`, `missing hash-chain fields`,
`broken previous_hash link`, `event hash mismatch`) — so running this tool
against a real audit file cannot itself become a leakage path.

## 27. Testing strategy

50+ new tests across 7 files
(`backend/tests/test_audit_*.py`), all self-contained — no real Vault
server, network access, database, or real credentials/PII required. A new
autouse fixture in `conftest.py` (`_isolate_audit_sink`) gives every test in
the suite an `InMemoryAuditSink` instead of writing into the real
`backend/var/audit/` directory (mirroring how encryption tests already use
`tmp_path` rather than the real `data/encrypted/`). The JSONL sink and
verification tool are tested separately against `tmp_path`. Critical
leakage tests pass clearly-marked synthetic values
(`SYNTHETIC_PASSWORD_DO_NOT_LOG_111`, `SYNTHETIC_JWT_DO_NOT_LOG_222`,
`SYNTHETIC_VAULT_TOKEN_DO_NOT_LOG_333`, `SYNTHETIC_API_KEY_DO_NOT_LOG_444`,
`SYNTHETIC_ENCRYPTION_KEY_DO_NOT_LOG_555`, `SYNTHETIC_PII_DO_NOT_LOG_666`,
plus request-body and query-string marker variants) through representative
flows and assert the exact marker string is absent from every captured
event — never a real secret or real PII.

## 28. Local demonstration procedure

```powershell
cd backend
# 1. Run the app with the default (jsonl) sink:
uvicorn app.main:app --reload
# 2. In another terminal, generate some events:
curl.exe http://127.0.0.1:8000/api/v1/health/live -i    # see X-Request-ID
curl.exe -X POST http://127.0.0.1:8000/api/v1/auth/token `
  -d "username=analyst&password=wrong"                   # authentication.failed
# 3. Inspect the audit trail:
Get-Content var/audit/audit.jsonl | Select-Object -Last 5
# 4. Verify the hash chain:
python -m app.audit.verify var/audit/audit.jsonl
```

## 29. Current limitations

- No `DATA_VALIDATION`/`PII_PROCESSING`/`SECURITY_CONFIGURATION` events are
  emitted yet — reserved taxonomy members with no current call site (PII
  aggregate signal already rides the `INGESTION` events).
- No per-request `authentication.succeeded` event on ordinary authenticated
  API calls (only at login) — a deliberate volume-control decision (§11),
  not an oversight.
- `authorization.allowed` fires on every permission check, not just denials
  — acceptable volume for a hackathon scale, but a high-traffic production
  deployment might want this configurable.
- No client-IP field (§22).
- Single-process write serialization only — concurrent multi-process writes
  to the same JSONL file are not coordinated (§18).
- Hash chain is tamper-*evident*, not tamper-*proof* (§25) — full-file
  deletion or truncate-and-refork attacks are not detectable from the file
  alone.
- No audit-read API endpoint was added (an `AUDIT_READ` permission already
  existed in `app/identity/authorization/permissions.py` from an earlier
  phase, unused until now — exposing audit content over HTTP is a
  meaningful additional design surface intentionally left for a future
  phase rather than rushed here).
- No automated alerting on repeated audit-sink failures.

## 30. Production-hardening recommendations

Not implemented in this phase; documented as required follow-up before any
production use:

- Forward events to centralized, append-only / WORM storage or a SIEM
  rather than a local file.
- Restrict filesystem read/write permissions on the audit destination to a
  dedicated, least-privilege security account.
- Independent security account/project boundary, separate from the
  application's own runtime credentials.
- Defined retention policies and integrity monitoring (periodic
  `app.audit.verify` runs, or continuous ingestion into a system that
  verifies as it consumes).
- NTP-synchronized clocks across all instances (timestamp integrity assumes
  a trustworthy system clock — not independently verified here).
- Alerting when the audit pipeline itself fails (this phase only logs a
  local warning; production should page someone).
- Backup and disaster-recovery procedure for the audit trail itself.
- Consider making fail-**closed** auditing configurable for specific
  high-value operations, per §21.
