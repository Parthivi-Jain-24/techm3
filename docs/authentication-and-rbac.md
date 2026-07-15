# Authentication & RBAC (Phase 4)

## 1. Scope

Implemented: OAuth2-compatible local **password token flow**, short-lived
**HS256 JWT** access tokens, **Argon2id** password hashing, canonical
**Principal** model, explicit **roles** and **permissions**, one central
**role→permission** mapping, reusable FastAPI **authentication** and
**authorization** dependencies, correct **401 vs 403**, **default-deny**, a
**service-identity** foundation, security-header middleware, and clean
integration with the Phase 3 privacy boundary.

**Not** implemented here (later phases / production hardening): API ingestion
(Phase 5), AES-256 (Phase 6), TLS 1.3 (Phase 7), secrets vault (Phase 8), full
audit middleware, PostgreSQL/persistent users, refresh tokens, OAuth2
authorization-code flow, OIDC/SSO, MFA.

## 2. Authentication architecture

```
POST /api/v1/auth/token (username+password, OAuth2 form)
  → DevelopmentIdentityProvider.authenticate() → Argon2id verify
  → short-lived HS256 JWT (sub, principal_type, iat, exp, jti)
Authorization: Bearer <token>
  → decode + validate JWT (signature, expiry, required claims, alg allow-list)
  → re-resolve CURRENT principal from the identity provider (source of truth)
  → active check → Principal
  → require_permission(...) → RBAC decision → privacy/minimization → operation
```

## 3–5. OAuth2 flow & why it's development-oriented

This is a **local password (Resource Owner Password) flow** for development,
automated testing, and hackathon demo. It is **not** a production SSO /
authorization server. Production should use **OAuth2 Authorization Code + PKCE**
and **OpenID Connect** via an external trusted IdP; the identity-provider
abstraction (`IdentityProvider` protocol) is designed so that swap needs no
change to the authentication/authorization logic.

## 6–7. Principal & identity types

`Principal` = `{principal_id, principal_type, roles, is_active}`. It carries **no
password, no token, no PII**, and **no permissions** (those are derived). Types:
`USER` (human) and `SERVICE` (machine). The internal `PrincipalRecord` (which
holds the Argon2 `password_hash`) never leaves the identity-provider layer and
is never returned by any API.

## 8. Roles

`ADMIN`, `COMPLIANCE_ANALYST`, `COMPLIANCE_REVIEWER`, `DATA_ENGINEER`,
`AUDITOR`, `SERVICE_ACCOUNT`.

## 9. Permissions

`KYC_READ`, `KYC_INGEST`, `KYC_VIEW_SENSITIVE`, `DATA_QUALITY_READ`,
`PII_CLASSIFICATION_READ`, `AUDIT_READ`, `SECURITY_ADMIN`.

## 10. Role → permission matrix (the single source of truth)

| Role | KYC_READ | KYC_INGEST | KYC_VIEW_SENSITIVE | DATA_QUALITY_READ | PII_CLASSIFICATION_READ | AUDIT_READ | SECURITY_ADMIN |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| ADMIN | | | | | ✓ | ✓ | ✓ |
| COMPLIANCE_ANALYST | ✓ | | ✓ | ✓ | ✓ | | |
| COMPLIANCE_REVIEWER | ✓ | | | | ✓ | | |
| DATA_ENGINEER | ✓ | ✓ | | ✓ | | | |
| AUDITOR | | | | | ✓ | ✓ | |
| SERVICE_ACCOUNT | | | | | | | |

## 11. Least privilege

ADMIN is security/config admin — **not** blanket customer-KYC access.
DATA_ENGINEER has no `SECURITY_ADMIN`; AUDITOR has no `KYC_INGEST`;
COMPLIANCE_ANALYST has no `SECURITY_ADMIN`. `SERVICE_ACCOUNT` grants **nothing**
by itself — a service gains capability only by also holding a narrow functional
role, and never inherits ADMIN.

## 12. Default deny

Access is denied for: missing/malformed/expired token, invalid signature,
unsupported algorithm, missing required claim, unknown principal, inactive
principal, unknown role (grants nothing), unknown permission, and empty
authorization policy.

## 13–15. JWT

Claims: `sub`, `principal_type`, `iat`, `exp`, `jti` — **no** roles/PII/secrets.
(Authorization is re-resolved from the provider, so token contents can't
elevate.) Expiry: `ACCESS_TOKEN_EXPIRE_MINUTES`, default **15** (validated > 0).
Signing: HS256 with `JWT_SECRET_KEY` from the environment (**never** hardcoded;
empty in `.env.example`); algorithm allow-list `{HS256}` — `none` and algorithm
confusion are rejected.

## 16. Password hashing

**Argon2id** via `argon2-cffi`. No custom crypto, no plaintext/MD5/SHA-1/raw
SHA-256/reversible encryption. Verification never raises (wrong password →
`False`) and never logs inputs. A dummy verify equalizes timing for unknown
usernames (no user enumeration). Login failures return a generic
`Invalid credentials` (never "no such user" vs "wrong password").

## 17. 401 vs 403

`401 Could not validate credentials` — not authenticated (no/invalid/expired
token, unknown/inactive principal). `403 Insufficient permissions` —
authenticated but lacking the required permission. The authorization dependency
depends on the authentication dependency, so 401 always precedes 403.

## 18. Privacy integration

Authorization decides **whether** an operation is allowed and selects a Phase 3
`ProcessingContext` (`kyc_context_for`); the **privacy** layer produces the
masked/minimized representation. `KYC_READ` does **not** return raw fields —
`kyc_context_for` maps read-only access to a masked context and only
`KYC_VIEW_SENSITIVE` to the un-minimized view. Masking logic is **not**
duplicated in the identity layer.

## 19. Service identity foundation

`ServiceIdentity` → a `Principal` with `principal_type=SERVICE`, distinguishable
from users, holding only its explicit functional-role permissions, never
auto-admin. Designed for future audit attribution. Future production options
(not implemented): client-credentials flow, mTLS, service-mesh / cloud workload
identity.

## 20. Current limitations

- Password flow + in-memory dev provider (no persistent user store).
- Single HS256 shared secret; no key rotation / JWKS; no token revocation list
  (short expiry mitigates).
- No refresh tokens, MFA, SSO, or rate limiting.
- Audit events are *designed for* but not yet emitted (full middleware later).

## 21. Production-hardening requirements

OAuth2 Authorization Code + PKCE / OIDC via an external IdP; persistent
identity store; asymmetric signing (RS256/EdDSA) + JWKS + key rotation; token
revocation/refresh; MFA; rate limiting and lockout; secret from a vault
(Phase 8); TLS 1.3 (Phase 7); full audit middleware capturing
`AUTHENTICATION_SUCCESS/FAILURE`, `AUTHORIZATION_GRANTED/DENIED`,
`SERVICE_IDENTITY_USED`.

## Running locally

```bash
# From backend/ — set a strong secret and (optionally) demo identities:
export JWT_SECRET_KEY="$(python -c 'import secrets;print(secrets.token_urlsafe(48))')"
# Generate an Argon2id hash for a demo password, then put it in DEV_AUTH_USERS:
python -c "from app.identity.authentication.password import hash_password as h; print(h('demo-pass'))"
export DEV_AUTH_USERS='[{"username":"demo","principal_id":"U-DEMO","password_hash":"<hash>","roles":["data_engineer"]}]'
uvicorn app.main:app --reload

# Demo: POST /api/v1/auth/token (form: username, password) -> bearer token
#       GET  /api/v1/security/me                 (Authorization: Bearer ...)
#       GET  /api/v1/security/data-quality-access-check  (needs DATA_QUALITY_READ)

# Tests (no network / DB / real creds; injected test secret):
python -m pytest
```
