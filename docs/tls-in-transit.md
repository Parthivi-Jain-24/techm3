# TLS 1.3 Encryption in Transit (Phase 7)

## 1. Scope

A credible, reproducible **TLS 1.3 encryption-in-transit boundary** for
inbound traffic to this FastAPI application, demonstrated locally. TLS is
terminated **outside FastAPI business logic** — no route handler, service, or
Phase 6 AES-256-GCM code claims to "encrypt" HTTP traffic. This phase does not
implement mTLS, certificate pinning, or a production PKI/ACME pipeline.

## 2. TLS architecture

```
Client
   │  HTTPS / TLS 1.3
   ▼
Uvicorn (TLS termination, in-process)
   │  plaintext ASGI call (in-process, not network-exposed)
   ▼
FastAPI application
```

## 3. Why TLS is terminated outside business logic

TLS is a transport-layer concern. Route handlers, `EncryptionService` (Phase
6), and privacy/minimization code have no certificate or protocol-negotiation
logic — that would conflate transport security with data-at-rest encryption
(different problems; see §19). Certificate loading and protocol enforcement
live in exactly one place: `backend/app/core/tls.py` (pure config/validation,
no route code) plus the deployment entrypoint that wires it into Uvicorn.

## 4. TLS termination technology selected

**Direct Uvicorn TLS termination**, via Uvicorn's `ssl_context_factory` hook.
This project has **no existing reverse proxy, Nginx, Caddy, Traefik, or
Dockerfile** — only a placeholder `docker-compose.yml` (Postgres only; backend
service commented out) and empty infra scaffold directories. Introducing a
full reverse-proxy container stack purely to demonstrate TLS would be
disproportionate infrastructure for this phase. Uvicorn 0.51's
`ssl_context_factory` parameter lets us build a standards-compliant
`ssl.SSLContext` and pin its protocol range explicitly — no custom TLS, no
hand-rolled crypto.

## 5. Strict TLS 1.3 demonstration profile

`app/core/tls.py::build_strict_tls13_context_factory()`:
1. Validates the configured cert/key files exist (fails closed — raises
   `TLSConfigurationError` rather than falling back to plaintext).
2. Returns a factory that lets Uvicorn build its normal `SSLContext` (loading
   the cert chain) and then **explicitly sets**:
   ```python
   context.minimum_version = ssl.TLSVersion.TLSv1_3
   context.maximum_version = ssl.TLSVersion.TLSv1_3
   ```
   This is a hard protocol-range pin, not a preference — the TLS stack itself
   refuses to complete a handshake below or above TLS 1.3. `STRICT_TLS_VERSION`
   is a fixed Python constant, **not environment-configurable**, so it cannot
   be silently weakened via `.env`.

## 6. Local development HTTP mode

```
uvicorn app.main:app --reload   →   http://127.0.0.1:8000
```
Ordinary FastAPI development/testing. **No TLS.** Never presented as
production transport security. All 275 automated tests run against this mode
(in-process ASGI, no network/TLS involved at all).

## 7. Secure HTTPS demonstration mode

```
python deployment/run_https_dev.py   →   https://localhost:8443
```
Entirely separate process/port from mode 6. Uses the strict TLS 1.3 profile
above. Binds to `127.0.0.1` only (not `0.0.0.0`).

## 8. Certificate strategy

| Environment | Strategy |
|---|---|
| Local development | plain HTTP, no certificate |
| Local TLS demonstration | self-signed cert generated locally via OpenSSL (below) |
| Production | trusted CA / managed load balancer or ingress / ACME (Let's Encrypt) / organizational PKI |

No production certificate exists in, or is claimed by, this repository.

## 9. Private-key handling

The private key never leaves the local filesystem. `app/core/tls.py` only
reads `settings.tls_key_path` (externalized, see §16) to hand to Uvicorn's
cert-loading — it never appears in source, logs, or exceptions.

## 10. Git-ignore behavior

`.gitignore` additions (Phase 7):
```
certs/
*.crt
*.pfx
*.p12
```
(in addition to the pre-existing broad `*.pem` / `*.key` rules). A static test
(`test_no_real_private_key_committed`) asserts `git ls-files certs/` is empty.

## 11. HTTPS endpoint

`https://localhost:8443` (configurable via `TLS_PORT`).

## 12. HTTP-to-HTTPS behavior

No HTTP listener is exposed by the secure demonstration profile itself (mode 7
binds only the HTTPS port) — there is nothing to redirect *from* in this
architecture. Mode 6 (plain HTTP, port 8000) and mode 7 (HTTPS, port 8443) are
two **separate, independently-started processes**; developers choose which to
run. A production reverse proxy would typically add a `:80 → 301 :443`
redirect — documented as a production recommendation (§24), not implemented
here since no such proxy exists yet.

## 13. Proxy trust boundary

`settings.trusted_proxy_ips` (env `TRUSTED_PROXY_IPS`) defaults to **empty —
trusts no proxy**. If set, it is passed to Uvicorn's own
`forwarded_allow_ips`, which trusts `X-Forwarded-*` **only from that exact
IP/CIDR**. It must never be `"*"` (static test asserts the default is not
`"*"`). Our own `SecurityHeadersMiddleware` never reads `X-Forwarded-*`
headers itself (verified by a static test) — a client-supplied
`X-Forwarded-Proto: https` header cannot flip HSTS or any other behavior; only
Uvicorn's TLS termination (or an explicitly trusted proxy) determines the ASGI
scope's real `scheme`.

## 14. Forwarded-header handling

Not needed in the current architecture: Uvicorn terminates TLS in-process, so
`request.url.scheme` is set natively to `"https"` — no forwarded-header
parsing is required for correct scheme detection in mode 7.

## 15. HSTS behavior

`SecurityHeadersMiddleware` (`app/core/security.py`) adds
`Strict-Transport-Security: max-age=86400` **only when
`request.url.scheme == "https"`** — never on plain HTTP (test-verified: absent
under `http://`, present under `https://`, and unaffected by a spoofed
`X-Forwarded-Proto: https` header sent to the plain-HTTP app). No
`includeSubDomains` (no subdomain architecture exists) and no `preload` (not
submitted/eligible). **HSTS does not itself encrypt anything** — it only tells
compliant clients to prefer HTTPS for *future* requests to this host; TLS
provides the actual encryption.

## 16. TLS cipher handling

No custom cipher list is configured — TLS 1.3 cipher suites are selected by
OpenSSL's modern secure defaults (confirmed live: `TLS_AES_256_GCM_SHA384`,
observed via `openssl s_client`, see §20). No RC4/DES/3DES/NULL/export/
anonymous ciphers are configured anywhere; TLS 1.2-era cipher-string tuning
does not apply to TLS 1.3's suite negotiation.

## 17. Health endpoint behavior

`/api/v1/health/live` and the legacy `/health` are unmodified and reachable
through the secure listener — live-verified: `200 {"status":"alive"}` over
`https://localhost:8443/api/v1/health/live`.

## 18. Swagger/OpenAPI behavior

`/docs` and `/openapi.json` are unmodified and reachable through the secure
listener — live-verified: both return `200` over HTTPS.

## 19. Outbound API TLS distinction

Phase 5's **outbound** API-ingestion client is untouched: HTTPS is still
required for non-test external sources, certificate verification is never
disabled (`verify=False` absent from application code — static test), and no
TLS warnings are suppressed. This is a *different* boundary from Phase 7's
*inbound* TLS termination:

```
INBOUND:  Client → TLS 1.3 (our listener) → FastAPI
OUTBOUND: Our backend → HTTPS + cert verification → trusted external API
```

We do not claim every external API supports only TLS 1.3 — that is out of our
control and unverified for arbitrary third parties.

## 20. Manual TLS 1.3 verification (PowerShell / Windows)

```powershell
# 1. Generate a local dev certificate (once):
pwsh scripts/setup/generate-dev-tls-cert.ps1

# 2. Start the secure listener:
python deployment/run_https_dev.py

# 3. In another terminal — health check over HTTPS (curl.exe, NOT the
#    PowerShell `curl` alias for Invoke-WebRequest; -k = accept the local
#    self-signed cert for THIS transport-connectivity test only):
curl.exe -k https://localhost:8443/api/v1/health/live

# 4. Prove TLS 1.3 succeeds:
openssl s_client -connect localhost:8443 -tls1_3
# Expected (observed in this session):
#   New, TLSv1.3, Cipher is TLS_AES_256_GCM_SHA384
#   Protocol: TLSv1.3
```

Actually observed output (this session):
```
subject=CN=localhost, O=Continuous KYC Autonomous Auditor (local dev only)
New, TLSv1.3, Cipher is TLS_AES_256_GCM_SHA384
Protocol: TLSv1.3
Verify return code: 18 (self-signed certificate)
```
(`Verify return code: 18` is expected and benign for a local self-signed cert
— see §22.)

## 21. TLS 1.2 rejection verification

```powershell
openssl s_client -connect localhost:8443 -tls1_2
```
Actually observed output (this session) — the handshake fails outright:
```
error:0A000126:SSL routines::unexpected eof while reading
no peer certificate available
SSL handshake has read 0 bytes and written 198 bytes
New, (NONE), Cipher is (NONE)
```
Also confirmed via curl: `curl.exe -sk --tls-max 1.2 https://localhost:8443/...`
→ connection fails (curl exit code 35 / `HTTP:000`), while
`curl.exe -sk --tlsv1.3 https://localhost:8443/...` → `HTTP:200`.

> **Note on TLS 1.0/1.1:** the OpenSSL client available in this environment
> (3.5.5) no longer negotiates TLS 1.0/1.1 at all (industry-wide deprecation),
> so `-tls1`/`-tls1_1` silently renegotiate at 1.3 instead of demonstrating a
> live rejection — this is a limitation of the *test client*, not evidence
> either way about the server. The server-side guarantee for TLS 1.0/1.1 (and
> 1.2) comes from the same `minimum_version = maximum_version = TLSv1_3`
> pin verified in §21 for TLS 1.2 and covered by static configuration tests
> (`test_tls10_not_enabled_in_strict_profile`,
> `test_tls11_not_enabled_in_strict_profile`) asserting
> `ssl.TLSVersion.TLSv1 < context.minimum_version` and
> `ssl.TLSVersion.TLSv1_1 < context.minimum_version`.

## Swagger/health over HTTPS (also observed this session)

```
curl.exe -sk https://localhost:8443/docs         → 200
curl.exe -sk https://localhost:8443/openapi.json → 200
curl.exe -sk -D - https://localhost:8443/api/v1/health/live
  → strict-transport-security: max-age=86400
  → x-content-type-options: nosniff
  → x-frame-options: DENY
```

## 22. Local self-signed certificate limitations

`openssl s_client` reports `Verify return code: 18 (self-signed certificate)`
and browsers/curl (without `-k`) will show a trust warning — **this is
expected**, not a bug. `-k` (or `-k`/`--insecure`) is used here **only** to
prove transport connectivity/protocol negotiation locally; it is never used as
evidence of production certificate validation, and it is never used in any
application code (outbound `httpx` calls keep default verification — §19).
Certificate **trust** (who issued it, is it in a trust store) is a separate
concern from transport **encryption** (which TLS 1.3 provides regardless of
trust-chain validity).

## 23. Production certificate requirements

A certificate from a trusted CA (or a managed load balancer / ingress that
handles this automatically), or an automated ACME (Let's Encrypt-style)
workflow, or organizational PKI. Never a self-signed cert in production.

## 24. Production deployment recommendation

```
Internet Client
      │
      ▼
Managed Load Balancer / Ingress / Reverse Proxy   (TLS 1.3 termination,
      │                                             trusted CA certificate,
      │  HTTP→HTTPS redirect, e.g. 301)
      ▼
Private Application Network
      │
      ▼
FastAPI Service (Uvicorn/Gunicorn workers)
```

Depending on the threat model, production may also require **end-to-end TLS**
between edge and backend, **mTLS**, or a **service mesh** — these are
documented options, not implemented in Phase 7 (see §26).

## 25. Current limitations

- Local demonstration only: direct Uvicorn TLS termination, not a
  production-grade reverse proxy/ingress.
- Self-signed certificate (expected local-dev trust warnings).
- No HTTP→HTTPS redirect exists (no HTTP listener is exposed by the secure
  profile to redirect from).
- No mTLS, no certificate pinning (deliberately out of scope — §U/§V of the
  Phase 7 spec).
- `forwarded_allow_ips`/`TRUSTED_PROXY_IPS` support exists but is unused by
  default (no reverse proxy is deployed yet).

## 26. Production-hardening options

Managed TLS termination (cloud load balancer / ingress) with automatic
certificate rotation; HTTP→HTTPS redirect at the edge; end-to-end TLS to the
backend or mTLS between services if the threat model requires it; a service
mesh for internal traffic encryption; OCSP stapling / modern cipher policy
managed by the edge provider; regular certificate-expiry monitoring.
