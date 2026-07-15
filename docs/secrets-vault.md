# Secrets Vault Integration (Phase 8)

## 1. Scope

A real, vault-backed `SecretProvider` implementation behind the existing
Phase 5 abstraction, so application secrets (encryption keys, API-ingestion
credentials) can be resolved from a dedicated secrets-management system
instead of source code, Git, config files, request bodies, encrypted
envelopes, or logs. Two explicit, non-overlapping modes: **environment**
(local development, unchanged from Phase 5/6) and **vault** (HashiCorp Vault
KV v2, new this phase).

## 2. Why secrets need a dedicated provider boundary

A `.env` file, Base64 encoding, an encrypted JSON blob beside the app, or a
hardcoded dict are **not** a secrets vault — they're all just storage
alongside the application, readable by anything that can read the
application's own files/environment. A real vault provides access control,
audit trails, and a boundary independent of the application's own filesystem —
none of which exist for a `.env` file. The `SecretProvider` abstraction lets
the *type* of backend change without the application caring which one is in
use.

## 3. Existing `SecretProvider` abstraction (unchanged)

`backend/app/secrets/provider.py`:
```python
class SecretProvider(Protocol):
    def get_secret(self, logical_name: str) -> str | None: ...
```
Every consumer (`EncryptionService`, `ApiConnector`) depends on this
interface only — never on a concrete provider or a Vault client directly.
This is unchanged since Phase 5.

## 4. `EnvironmentSecretProvider`

Unchanged: resolves a logical name from `os.environ` (or an injected mapping
in tests). **This is the local-development provider, not a production
secrets-management system.**

## 5. `VaultSecretProvider` (new)

`backend/app/secrets/vault_provider.py`. Resolves logical secret names from
ONE configured HashiCorp Vault KV v2 path via the official `hvac` client.
Implements the *exact same* `get_secret(logical_name) -> str | None` contract
as `EnvironmentSecretProvider` — this is why `EncryptionService` and
`ApiConnector` required **zero changes**.

## 6. Provider selection

`backend/app/secrets/factory.py::resolve_secret_provider()` is the **single**
place `SECRETS_PROVIDER` is interpreted:
```
SecretProvider
    ├── EnvironmentSecretProvider   (SECRETS_PROVIDER=environment, default)
    └── VaultSecretProvider         (SECRETS_PROVIDER=vault)
```
`get_secret_provider()` (the Phase 5/6 import path, unchanged) delegates to
this factory. Unknown values raise `UnsupportedSecretProviderError`.

## 7. Environment mode

`SECRETS_PROVIDER=environment` (default — preserves all Phase 5/6 behavior
exactly). Secrets resolved from `os.environ`.

## 8. Vault mode

`SECRETS_PROVIDER=vault`. Every `get_secret()` call resolves through
`VaultSecretProvider` against the configured Vault KV v2 mount/path.

## 9. Fail-closed behavior

If `SECRETS_PROVIDER=vault` and Vault is unreachable, authentication fails, or
configuration is incomplete, the operation **raises** — it never silently
returns an environment-resolved value instead. Proven by
`test_vault_mode_does_not_silently_fall_back_to_environment`: Vault mode +
unreachable Vault + the *same* secret name *also* present in the environment
→ the call still fails.

## 10–11. Selected technology

**HashiCorp Vault**, **KV Secrets Engine v2**, via the official `hvac` Python
client. No existing secrets platform (AWS/Azure/GCP Secrets Manager) was found
in this repository (grep-confirmed clean before implementation).

## 12–13. Mount point & application secret path

Configurable, non-secret: `VAULT_MOUNT_POINT` (default `secret`),
`VAULT_SECRET_PATH` (default `continuous-kyc`) → full KV v2 location
conceptually `secret/data/continuous-kyc`.

## 14. Logical secret naming

Callers request a logical name only (`kyc-data-key-v1`,
`trusted-kyc-provider-token`, ...) — never a Vault path. `VaultSecretProvider`
always reads the *same configured* path and looks up the requested key within
that one JSON blob. There is no parameter, anywhere, through which a caller
can supply an arbitrary mount/path (`get_secret(self, logical_name)` — no
`path` argument exists).

## 15. Vault authentication

Token authentication (`VAULT_AUTH_METHOD=token`) — the only method
implemented in Phase 8, chosen for local hackathon demonstration. Any other
value raises `SecretConfigurationError` (explicit allow-list, not a dynamic
import).

## 16. Bootstrap credential problem

The application needs *some* credential to authenticate to Vault before it
can fetch anything else — that credential can't itself come from Vault
(circular). `VAULT_TOKEN` is read **directly from the process environment**
inside `VaultSecretProvider.__init__` — the one deliberate, documented
exception to "secrets go through `SecretProvider`". It is **not** a
`pydantic-settings` field (not loaded from `.env`), so it never appears in
`Settings`, config dumps, or any place ordinary configuration is inspected.

## 17. Vault token safety

Never hardcoded, never committed, never logged, never included in exception
messages (tests assert this explicitly), never placed in a URL/query string.
`.env.example` documents the variable name only — with an explicit comment
that a real value must never go there.

## 18. Local Vault dev mode

`hashicorp/vault:1.15` container (or `vault server -dev` binary) in **dev
mode** — commented out by default in `docker-compose.yml`, matching the
existing `backend`/`frontend` placeholder pattern.

## 19. Why dev mode is not production-ready

Vault dev mode is **in-memory** (all data lost on restart), auto-unsealed,
uses a single fixed root token, and runs over plain HTTP. It is explicitly
labeled `LOCAL DEV-MODE ONLY` in `docker-compose.yml` and throughout this
document. It must never be mistaken for a production Vault deployment.

## 20. TLS requirements for production Vault communication

Production Vault communication must use `https://` with certificate
verification (`hvac.Client` uses `requests` defaults — verification is
**never** disabled; no `verify=False` exists anywhere in this codebase — grep
and static-test verified). Local dev-mode `http://127.0.0.1:8200` is permitted
**only** as an explicitly documented local-development exception — never
presented as production-secure.

## 21. AES-256-GCM integration

`EncryptionService` (Phase 6) is **unchanged**. It already called
`resolve_key(secret_provider, key_id)` → `secret_provider.get_secret(key_id)`;
now `secret_provider` may be a `VaultSecretProvider` instead of
`EnvironmentSecretProvider` — nothing in `app/encryption/service.py`,
`app/encryption/keys.py`, the AES-GCM algorithm, nonce generation, envelope
format, or `key_id` semantics changed. Proven end-to-end with a synthetic key
served by a fake Vault client (no real Vault server required for tests).

## 22. API-ingestion credential integration

`ApiConnector` (Phase 5) is **unchanged**. It already called
`self._secrets.get_secret(source.auth_secret_name)`; that now works
transparently with `VaultSecretProvider`. Proven with a synthetic API token
served by a fake Vault client, producing the correct `Authorization: Bearer
...` header with no connector code changes.

## 23. Secret rotation readiness

No automated rotation engine is implemented. What Phase 8 preserves:
- **API credentials**: `ApiConnector` retrieves the current secret at request
  time (never embeds it in source config), so rotating the Vault-stored value
  changes the *next* retrieval automatically.
- **Encryption keys**: `key_id` in the encrypted envelope allows a future key
  to be introduced under a new `key_id` without touching old envelopes.

## 24. Encryption-key rotation warning

**Do not delete an old encryption key from Vault while any encrypted artifact
still references its `key_id`.** Existing ciphertext can only be decrypted
with the exact key material that encrypted it — premature deletion makes that
data permanently unrecoverable. A future rotation process must decrypt with
the old key and re-encrypt under a new `key_id` *before* the old key is
retired; Phase 8 does not implement this automatically.

## 25. Logging safety

Neither `VaultSecretProvider` nor `EncryptionService`/`ApiConnector` log
anything. Tests assert, using clearly-marked synthetic values
(`SYNTHETIC_VAULT_SECRET_DO_NOT_LOG_987654`,
`SYNTHETIC_VAULT_TOKEN_DO_NOT_LOG_abcxyz`), that: the Vault token, retrieved
secret values, encryption keys, and API credentials never appear in captured
log output, and full Vault response bodies are never logged (only a safe,
generic message on error).

## 26. Health/readiness behavior

`/api/v1/health/live` remains **fully independent of Vault** — configuring
`SECRETS_PROVIDER=vault` with an unreachable address does not affect it
(test-verified: still returns `200 {"status":"alive"}`). No new
health/readiness endpoint was added (there was no pre-existing `/ready`
endpoint to extend, and the Phase 8 spec prefers no new public endpoint unless
clearly necessary — verified `/api/v1/health/ready` still 404s).

## 27. Local demonstration procedure

See §"Local demonstration commands" below. **This procedure has been executed
live** against a real `hashicorp/vault:1.15` Docker container (not just
validated via the fake test client) — see the verification note at the end of
that section for exactly what was proven.

## 28. Automated testing strategy

All Phase 8 tests use a fake in-process Vault client
(`tests/_vault_helpers.py`) that mimics only the exact `hvac.Client` shape the
provider calls (`client.secrets.kv.v2.read_secret_version(...)`) — **no real
Vault server, Docker, or network access is required** for `python -m pytest`.
50 focused tests cover provider selection, environment-provider regression,
Vault configuration/auth/retrieval/KV-v2 behavior, encryption integration, API
credential integration, fail-closed/no-fallback behavior, logging safety, and
health independence.

## 29. Current limitations

- Token auth only (no AppRole/Kubernetes/cloud-IAM auth implemented).
- No secret-value caching (every `get_secret()` call hits Vault directly in
  vault mode — acceptable for hackathon scale; a bounded TTL cache is a future
  option, not implemented).
- No automated rotation engine.
- Local dev-mode Vault only demonstrated (in-memory, non-HA, HTTP).
- No new health/readiness endpoint reports Vault connectivity status.

## 30. Production-hardening requirements

Workload-native authentication (AppRole, Kubernetes auth, cloud IAM auth) to
eliminate long-lived static tokens; Vault deployed in HA/production mode with
persistent storage and auto-unseal; TLS with a trusted certificate for all
Vault communication; fine-grained Vault policies (least privilege per
application/secret); audit logging enabled on the Vault server itself; secret
rotation automation with old-key retention until dependent ciphertext is
re-encrypted.

---

## Local demonstration commands (PowerShell)

```powershell
# 1. Start local Vault dev mode (Docker):
docker run --rm -p 8200:8200 --cap-add=IPC_LOCK `
  -e 'VAULT_DEV_ROOT_TOKEN_ID=dev-only-root-token' `
  hashicorp/vault:1.15 server -dev
# (or, if you have the Vault binary: vault server -dev)

# 2. In another terminal, configure the session:
$env:VAULT_ADDR = "http://127.0.0.1:8200"
$env:VAULT_TOKEN = "dev-only-root-token"

# 3. Generate a synthetic AES-256 key locally (never commit it):
$key = python -c "import os, base64; print(base64.b64encode(os.urandom(32)).decode())"

# 4. Write it into the configured KV v2 path (value not printed after this):
vault kv put secret/continuous-kyc kyc-data-key-v1="$key"
# or via the HTTP API if the vault CLI isn't installed:
curl.exe -s -X POST -H "X-Vault-Token: $env:VAULT_TOKEN" `
  -d "{\"data\":{\"kyc-data-key-v1\":\"$key\"}}" `
  "$env:VAULT_ADDR/v1/secret/data/continuous-kyc" | Out-Null

# 5. Select vault mode for the backend:
$env:SECRETS_PROVIDER = "vault"

# 6. Run the existing Phase 6 verification job (synthetic data only):
cd backend
python -m app.encryption.jobs.verify_encryption
# NOTE: that job builds its OWN in-memory demo key by default and does not
# read SECRETS_PROVIDER; to see it resolve through Vault specifically, use
# the equivalent programmatic check documented in this repo's test suite
# (tests/test_secrets_encryption_integration.py), which exercises the same
# EncryptionService API against a Vault-backed provider.

# 7. Stop the local Vault dev server (Ctrl+C in its terminal, or):
docker ps --filter ancestor=hashicorp/vault:1.15 -q | ForEach-Object { docker stop $_ }
```

> **Live execution record.** This sequence was executed against a real,
> running `hashicorp/vault:1.15` dev-mode container (Docker Desktop), not just
> validated via the fake test client. What was actually observed:
>
> 1. Container started (`docker run -d --rm --cap-add=IPC_LOCK
>    -e VAULT_DEV_ROOT_TOKEN_ID=dev-only-root-token hashicorp/vault:1.15
>    server -dev`); `GET /v1/sys/health` returned `200`; `GET /v1/sys/mounts`
>    confirmed a KV v2 mount at `secret/`.
> 2. A synthetic, locally-generated 32-byte key was written to
>    `secret/data/continuous-kyc` under `kyc-data-key-v1` via the HTTP API —
>    the value itself was never printed, only its presence/length.
> 3. The real `VaultSecretProvider` (the actual class, not the fake test
>    double) retrieved that key from the live container, and the real
>    `EncryptionService` used it to encrypt and decrypt a synthetic record,
>    with a byte-for-byte round-trip match and no raw key material present in
>    the stored envelope.
> 4. A second synthetic secret (`trusted-kyc-provider-token`) was added the
>    same way, and the real (unmodified) `ApiConnector` resolved it end-to-end
>    into a correct `Authorization: Bearer <redacted>` header.
> 5. A real authentication failure (wrong token against the live server)
>    raised `SecretAuthenticationError`; a real lookup of a nonexistent
>    logical name returned `None` — both against the live container, not a
>    mock.
> 6. **No-fallback proof:** the live container was stopped
>    (`docker stop kyc-vault-demo`), an environment variable
>    `kyc-data-key-v1=THIS-MUST-NEVER-BE-USED-AS-FALLBACK` was planted, and
>    with `SECRETS_PROVIDER=vault` still selected, the call raised
>    `SecretBackendUnavailableError` rather than silently reading the
>    environment value — the fail-closed guarantee holds against a real
>    outage, not just a simulated one.
> 7. The full automated test suite (325 tests) was re-run immediately after
>    and still passed, confirming the live demo left no side effects on the
>    (mock-based) test suite. The container was removed on stop (`--rm`); no
>    Vault data persists between runs since dev mode is entirely in-memory.
>
> The `hvac` client shape this container exercised is the exact same shape
> `tests/_vault_helpers.py` mimics for the no-Docker-required automated suite,
> so both the live run and `python -m pytest` are testing the same contract.
