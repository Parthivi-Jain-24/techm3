# Identity

**Owner:** Workstream 1 (Secure Data Ingestion, Authentication, Authorization, PII Protection, Database)

## Purpose

Authentication, authorization, RBAC, and service-account management for all human users and system/agent identities interacting with the platform.

## Structure

- `authentication/` — OAuth2/JWT-compatible login, token issuance, token validation.
- `authorization/` — permission checks, case-level authorization.
- `rbac/` — role definitions and role-to-permission mappings.
- `service_accounts/` — scoped credentials for internal services and AI agents.

## Inputs

User login credentials (never stored in plaintext), OAuth2 tokens, service-account requests from other modules.

## Outputs

Signed JWTs, authorization decisions (allow/deny), role/permission metadata consumed by `backend/app/api/dependencies.py` and every protected route.

## Public Interface Expectations

Other modules should depend on `backend/app/core/security.py` and `backend/app/core/permissions.py` for auth checks rather than reimplementing token/permission logic.

## Security Considerations

- JWT secrets come from environment variables only (`JWT_SECRET_KEY`).
- AI agents must receive scoped service-account credentials, never direct database access or standing human-equivalent permissions.
- All authentication/authorization failures must be logged via `backend/app/audit/`.

## Integration Dependencies

- `backend/app/core/security.py`, `backend/app/core/permissions.py` (shared entrypoints).
- `backend/app/audit/` for auth event logging.
