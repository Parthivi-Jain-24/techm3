# Demo Guide — Secure Data, Identity & Governance

A concise, copy-pasteable hackathon demo. **All values below are synthetic
placeholders** — never paste a real secret, key, or Vault token. Commands are
PowerShell (Windows). The backend virtual environment is `backend/.venv`.

> This is a **security-focused prototype** with a production-oriented
> architecture. TLS/Vault shown here are **local demonstration** profiles.

## 0. Prerequisites

- Python 3.12+ (validated on **3.14.5**).
- Docker Desktop (only for the optional live Vault demo).
- Working directory: `Desktop\techm code\continuous-kyc-autonomous-auditor`.

## 1. Environment setup

```powershell
cd "continuous-kyc-autonomous-auditor\backend"
.\.venv\Scripts\Activate.ps1     # or: python -m venv .venv ; ... ; pip install -r requirements.txt
```

## 2. Safe synthetic configuration (never real secrets)

```powershell
# JWT signing secret (demo only — any >=32-char throwaway string)
$env:JWT_SECRET_KEY = "demo-only-jwt-secret-please-change-0123456789"

# One demo identity (data_engineer). Generate the password HASH, never store a raw password:
$hash = python -c "from app.identity.authentication.password import hash_password; print(hash_password('demo-pass'))"
$env:DEV_AUTH_USERS = "[{""username"":""demo_engineer"",""principal_id"":""U-DEMO-ENG"",""password_hash"":""$hash"",""principal_type"":""user"",""roles"":[""data_engineer""],""is_active"":true}]"
```

## 3. Run the tests (proof it all works)

```powershell
python -m pytest                        # full suite: 483 passed
python -m pytest tests\integration      # Phase 10 E2E + acceptance + negative
```

## 4. Start the backend (plain HTTP dev mode)

```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

## 5. Health + request correlation

```powershell
curl.exe -i http://127.0.0.1:8000/api/v1/health/live
# -> 200 {"status":"alive"} and an `x-request-id:` header on every response
```

## 6. Authentication demo

```powershell
$tok = (curl.exe -s -X POST http://127.0.0.1:8000/api/v1/auth/token `
  -d "username=demo_engineer&password=demo-pass" | ConvertFrom-Json).access_token
# Wrong password -> 401:
curl.exe -s -o NUL -w "%{http_code}`n" -X POST http://127.0.0.1:8000/api/v1/auth/token -d "username=demo_engineer&password=WRONG"
```

## 7. RBAC demo

```powershell
# Authenticated, safe principal view (no password/hash/token):
curl.exe -s http://127.0.0.1:8000/api/v1/security/me -H "Authorization: Bearer $tok"
# Anonymous protected endpoint -> 401:
curl.exe -s -o NUL -w "%{http_code}`n" -X POST http://127.0.0.1:8000/api/v1/ingestion/api/kyc_provider/run
# (A role lacking kyc_ingest would get 403 — see docs/rbac-matrix.md.)
```

## 8. CSV ingestion demo (synthetic data)

```powershell
# Place a synthetic CSV in the approved dir, then:
python -m app.ingestion.jobs.run_kyc_ingestion clients_with_fatf_ofac.csv
# Prints a PII-safe aggregate summary only (counts, masked ids) — never raw rows.
```

## 9. XLSX ingestion demo (Phase 10)

```powershell
python -c "import openpyxl; wb=openpyxl.Workbook(); ws=wb.active; ws.append(['client_id','client_name','client_type','sector','sector_risk','country','pep_flag','sanctions_flag','fatf_country_flag']); ws.append(['1','Synthetic Co','Corporate','Tech','High','in','0','1','0']); wb.save('data/raw/kyc/demo.xlsx')"
python -m app.ingestion.jobs.run_kyc_ingestion demo.xlsx
# Same normalization/validation/audit pipeline as CSV; formulas never evaluated.
```

## 10. API ingestion demo

Trusted-source model: the caller supplies a **`source_id` only** (never a
URL). Configure a source via `API_SOURCES_JSON` and trigger
`POST /api/v1/ingestion/api/{source_id}/run` (requires `kyc_ingest`). The
automated tests (`tests/test_api_*.py`, `test_phase10_acceptance.py`) exercise
this end-to-end with a mocked transport — no real network. See
docs/api-ingestion.md.

## 11. AES-256-GCM encryption demo (synthetic key)

```powershell
python -m app.encryption.jobs.verify_encryption
# Self-contained: builds an in-memory random key, round-trips, and proves
# tamper + wrong-key both fail closed. No real key is printed or persisted.
```

## 12. TLS 1.3 demo (local self-signed)

```powershell
pwsh scripts\setup\generate-dev-tls-cert.ps1     # once; generates a git-ignored dev cert
python ..\deployment\run_https_dev.py            # from backend/ ; strict TLS 1.3 listener on :8443
# Verify negotiated protocol:
python -c "import ssl,socket; c=ssl._create_unverified_context(); s=c.wrap_socket(socket.create_connection(('127.0.0.1',8443)),server_hostname='localhost'); print(s.version())"
# -> TLSv1.3   (TLS 1.2 handshakes are rejected by design)
```

## 13. Vault demo (local dev container)

```powershell
docker run -d --rm --name kyc-vault-demo -p 8200:8200 --cap-add=IPC_LOCK `
  -e "VAULT_DEV_ROOT_TOKEN_ID=demo-only-root-token" hashicorp/vault:1.15 server -dev
$env:VAULT_ADDR = "http://127.0.0.1:8200"; $env:VAULT_TOKEN = "demo-only-root-token"
$env:SECRETS_PROVIDER = "vault"
# Store a SYNTHETIC key, then resolve through the real provider (see docs/secrets-vault.md
# "Local demonstration commands"). Fail-closed: stop Vault and the app raises, never falls back.
docker stop kyc-vault-demo
```

## 14. Audit-log demo

```powershell
# After exercising the app, view the structured JSONL (one event per line):
Get-Content backend\var\audit\audit.jsonl -Tail 5
# Each line: event_id, UTC timestamp, event_type, action, outcome, actor, resource,
# request_id, previous_hash, event_hash. No secrets, no raw PII.
```

## 15. Audit tamper-detection demo (hash chain)

```powershell
python -m app.audit.verify backend\var\audit\audit.jsonl
# -> "VALID chain: N event(s) verified".
# Edit any line in a COPY, re-run -> "INVALID chain: failure detected at line X".
```

## 16. Cleanup

```powershell
# Stop servers (Ctrl+C). Remove runtime artifacts (git-ignored, safe to delete):
Remove-Item backend\var\audit\*.jsonl -ErrorAction SilentlyContinue
Remove-Item data\encrypted\* -Recurse -ErrorAction SilentlyContinue
docker rm -f kyc-vault-demo 2>$null
# Never commit: certs/, .env, var/audit/*.jsonl, data/encrypted/*.
```
