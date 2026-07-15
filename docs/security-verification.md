# Security Verification (Phase 10)

Evidence-based static + dynamic security review of the **Secure Data,
Identity, and Governance** workstream. Each check records the result, the
evidence, and any residual limitation. No result here is claimed without a
test or a live observation.

**Language discipline (Part AL):** this is a *security-focused prototype* with
a *production-oriented architecture* and *defense-in-depth controls*. It is
**not** claimed to be production-ready, tamper-proof, immutable, or
compliance-certified.

## 1. Secret / private-key scan (Parts A/F)

| Check | Result | Evidence |
|-------|--------|----------|
| Private keys tracked in git | **CLEAN** | `git grep "BEGIN.*PRIVATE KEY"` → none; `git ls-files` shows no `.pem/.key/.env/.jsonl` |
| `.env` files tracked | **CLEAN** | none tracked; `.gitignore` covers `.env`/`.env.*` (keeps `.env.example`) |
| Runtime audit logs tracked | **CLEAN** | `backend/var/audit/**` git-ignored; only `.gitkeep` tracked |
| Encrypted artifacts tracked | **CLEAN** | `data/encrypted/**` git-ignored |
| TLS dev key committed | **CLEAN** | `certs/` git-ignored; `git ls-files certs/` empty; `git check-ignore certs/local/dev-key.pem` confirms ignored |
| Hardcoded secrets in code | **CLEAN** | only match was `vault_secret_path="continuous-kyc"` (a non-secret path) |
| `NotImplementedError` / placeholder in workstream | **CLEAN** | none; two TODO-grep hits were the word "hackathon" in docstrings |

No real secret was found. No STOP condition triggered.

## 2. Auth / tokens

| Check | Result | Evidence |
|-------|--------|----------|
| Hardcoded/weak JWT secret | **PASS** | `settings.jwt_secret_key` env-sourced, empty default → `AuthConfigError` (no issuance), never a literal |
| Signature verification disabled | **PASS** | `jwt.decode(..., algorithms=[...], options={"require":[...]})`; no `verify_signature=False` |
| Dynamic algorithm from token | **PASS** | explicit allow-list `SUPPORTED_ALGORITHMS={"HS256"}`; `alg="none"` rejected (`test_neg_unsupported_algorithm_rejected`) |
| Expiry enforced | **PASS** | `require` includes `exp`; `test_acceptance_jwt_expiry_enforced` |
| Token/Authorization header logged | **PASS** | audit leakage tests: JWT marker absent (`test_audit_leakage.py`, `test_e2e_jwt_marker_not_in_audit`) |
| Password storage/logging | **PASS** | Argon2id hash only (`password.py`); password marker absent from audit (`test_e2e_password_marker_not_in_audit`); no account enumeration on failure |

## 3. RBAC

| Check | Result | Evidence |
|-------|--------|----------|
| Endpoints missing authorization | **PASS** | protected routes use `require_permission`; only health/token/`/me` are intentionally public/auth-only (rbac-matrix.md) |
| Default-allow behavior | **PASS** | `require_permission*` fail closed; empty policy denies |
| User-controlled role escalation | **PASS** | principal re-resolved server-side each request; token claims cannot elevate |

## 4. Ingestion (CSV + XLSX)

| Check | Result | Evidence |
|-------|--------|----------|
| Path traversal / absolute path | **PASS** | `resolve_kyc_path` rejects `..`, absolute, symlink escape; `test_neg_path_traversal_rejected` |
| Unsafe / unrestricted extension | **PASS** | `SUPPORTED_EXTENSIONS={".csv",".xlsx"}`; `.exe`/`.txt` rejected (`test_neg_unsupported_extension_rejected`) |
| Unbounded file size | **PASS** | `validate_kyc_file` size limit (`max_kyc_file_size_mb`) |
| Unbounded XLSX rows (decompression bomb) | **PARTIAL** | `MAX_XLSX_ROWS=1e6` cap + compressed-size limit; a pathological zip-bomb is only partially mitigated — production needs AV/content-disarm (documented, kyc-ingestion.md) |
| XLSX formula evaluation | **PASS** | openpyxl `read_only=True, data_only=True` — never evaluates formulas; corrupt file → `CorruptFileError` (`test_neg_corrupt_xlsx_rejected`) |
| Formula/CSV injection on export | **N/A** | system never writes spreadsheet/CSV output |
| Raw PII logged | **PASS** | ingestion audit is aggregate-only; PII marker absent (`test_xlsx_ingestion.py::test_xlsx_ingestion_audit_has_no_raw_pii`, `test_e2e_..._pipeline_safe`) |

## 5. API ingestion (SSRF)

| Check | Result | Evidence |
|-------|--------|----------|
| Arbitrary caller URL | **PASS** | caller supplies `source_id` only; server-controlled `TrustedApiSourceConfig` |
| localhost / 127.0.0.1 / ::1 | **PASS** | `test_neg_ssrf_blocked_destinations` (parametrized) |
| Private IPv4 / link-local / metadata (169.254.169.254) | **PASS** | `security.py` rejects `is_private/is_loopback/is_link_local/is_multicast/is_reserved/is_unspecified`; same test |
| Userinfo in URL | **PASS** | `user:pass@host` rejected (`test_neg_ssrf_userinfo_rejected`) |
| HTTP external when HTTPS required | **PASS** | `test_neg_http_external_rejected_when_https_required` |
| Redirects bypass | **PASS** | `follow_redirects=False` by default |
| Timeout / response-size cap | **PASS** | explicit `httpx.Timeout`; streamed byte cap → `RESPONSE_TOO_LARGE` (`test_neg_oversized_api_response_rejected`) |
| TLS verify disabled | **PASS** | `verify=False` appears nowhere (only a comment forbidding it) |
| Credential / raw payload logged | **PASS** | markers absent (`test_e2e_secure_api_ingestion`, `test_audit_leakage.py`) |

## 6. Encryption at rest (AES-256-GCM)

| Check | Result | Evidence |
|-------|--------|----------|
| Key length (exactly 32 bytes) | **PASS** | `decode_key` rejects 16/24/31/33; `test_acceptance_aes_key_length_enforced` |
| Static / reused nonce | **PASS** | fresh `os.urandom(12)` per operation; `test_same_plaintext_twice_produces_different_output` |
| Unauthenticated encryption | **PASS** | AESGCM AEAD + AAD binding |
| Tamper / wrong-key detection | **PASS** | `InvalidTag`→`DecryptionFailedError`; `test_acceptance_aes_tamper_detected`, `test_neg_wrong_key_fails_closed` |
| Key material in envelope / logs | **PASS** | envelope has `key_id` only; markers absent (`test_e2e_vault_backed_encryption_round_trip`, `test_encryption_logging_privacy.py`) |
| Plaintext temp files | **PASS** | in-memory serialize→encrypt; atomic write (`artifact_store.py`) |

## 7. TLS 1.3 in transit (live-verified)

| Check | Result | Evidence |
|-------|--------|----------|
| Strict TLS 1.3 config applied | **PASS** | `core/tls.py` `minimum_version=maximum_version=TLSv1_3`; `test_tls_config.py` |
| Private key not committed | **PASS** | see §1 |
| HTTPS fails safely w/o cert | **PASS** | `test_missing_cert_fails_closed_not_silent_http_fallback` |
| `verify=False` introduced | **PASS** | absent |
| **Live handshake — negotiated protocol** | **PASS** | started `deployment/run_https_dev.py`; Python `ssl` client negotiated **`TLSv1.3`**, HTTP 200 over channel |
| **Live — TLS 1.2 rejected** | **PASS** | forcing `maximum_version=TLSv1_2` → handshake failed (`SSLEOFError`) |

Residual: local self-signed demonstration listener only — not a production
reverse proxy/ingress; no HSTS preload; no mTLS.

## 8. Secrets / Vault (mocked suite + live smoke)

| Check | Result | Evidence |
|-------|--------|----------|
| Provider selection centralized | **PASS** | `factory.resolve_secret_provider`; unknown name rejected (`test_secrets_factory.py`) |
| Fail-closed, no env fallback | **PASS** | `test_vault_mode_does_not_silently_fall_back_to_environment`, `test_e2e_vault_fail_closed_no_environment_fallback` |
| Vault token / value / full response logged | **PASS** | markers absent (`test_vault_provider.py` logging tests, `test_e2e_vault_fail_closed...`) |
| Arbitrary Vault paths | **PASS** | provider reads one configured path; `get_secret(logical_name)` has no path arg |
| No recursive secret→audit→secret loop | **PASS** | audit sink/service import no `app.secrets` (AST test `test_audit_subsystem_has_no_dependency_on_secret_provider`) |
| **Live smoke** | **PASS** | Docker `hashicorp/vault:1.15` dev; real `VaultSecretProvider` resolved a synthetic key; AES round-trip OK; key + token absent from audit; container removed |

## 9. Audit logging

| Check | Result | Evidence |
|-------|--------|----------|
| Request body / response body read | **PASS** | plain-ASGI middleware never calls `request.body()`; body/query markers absent (`test_e2e_body_and_query_markers_not_in_audit`) |
| Query string logged | **PASS** | only `scope["path"]` recorded, never query string |
| Full header / Authorization / Cookie logged | **PASS** | no header dump; `test_audit_leakage.py::test_cookies_and_full_headers_never_captured` |
| Unbounded metadata | **PASS** | depth/length/collection bounds (`test_audit_sanitize.py`) |
| User-controlled audit path | **PASS** | server-controlled; traversal falls back to approved default (`test_audit_sink_jsonl.py`) |
| Tamper evidence | **PASS (evident, not proof)** | SHA-256 chain; tamper/reorder/broken-link detected; verifier prints no event content |

## Residual limitations (carried forward)

- XLSX zip-bomb only partially mitigated (row cap + size limit).
- TLS/Vault are **local demonstration** profiles, not production deployments.
- Audit trail is tamper-**evident**, not tamper-proof (full-file
  delete/truncate-refork not detectable from the file alone).
- App-level SSRF controls only (DNS-rebinding/TOCTOU residual — needs network
  egress controls in production).
- `bandit`/`pip-audit` were **NOT RUN** — not configured in this repo and a
  dependency-audit scanner needs network access; see security-baseline.md and
  Part W. Static review above was performed manually instead.
