# RBAC Permission Matrix (Phase 10)

Derived directly from code — **not invented**:

- Roles: `app/identity/rbac/roles.py`
- Permissions: `app/identity/authorization/permissions.py`
- Central role→permission mapping: `app/identity/rbac/mappings.py`
- Enforcement: `app/identity/authorization/dependencies.py`
  (`require_permission` / `require_permissions`, fail-closed)
- Routes: `app/api/routes/`

Authorization is **permission-based, never role-name based**. Route handlers
require a `Permission`; roles grant permissions only via the central mapping.

## Role → Permission mapping

| Role | Permissions granted |
|------|---------------------|
| `admin` | `security_admin`, `audit_read`, `pii_classification_read` |
| `compliance_analyst` | `kyc_read`, `kyc_view_sensitive`, `pii_classification_read`, `data_quality_read` |
| `compliance_reviewer` | `kyc_read`, `pii_classification_read` |
| `data_engineer` | `kyc_ingest`, `data_quality_read`, `kyc_read` |
| `auditor` | `audit_read`, `pii_classification_read` |
| `service_account` | *(none — grants nothing by itself)* |

Key least-privilege properties (test-verified in `test_rbac.py`):

- `admin` is **not** blanket access — it holds security/config permissions,
  **not** `kyc_read` or `kyc_view_sensitive`.
- `service_account` grants **nothing** alone; a machine identity gains
  capability only by *also* holding a narrow functional role.
- An unknown role resolves to the empty permission set (no default-allow).

## Endpoint → required permission

| Method & path | Required permission | Allowed roles | Denied (authenticated) | Anonymous |
|---------------|---------------------|---------------|------------------------|-----------|
| `GET /api/v1/health/live` | *(none — public)* | everyone | — | 200 OK |
| `GET /health` (legacy) | *(none — public)* | everyone | — | 200 OK |
| `POST /api/v1/auth/token` | *(none — credential exchange)* | valid credentials | invalid creds → 401 | 401 on bad creds |
| `GET /api/v1/security/me` | *authentication only* | any authenticated principal | — | 401 |
| `GET /api/v1/security/data-quality-access-check` | `data_quality_read` | `compliance_analyst`, `compliance_reviewer`*(no)*, `data_engineer`, `admin`*(no)* | `auditor`, `admin`, `service_account` | 401 |
| `POST /api/v1/ingestion/api/{source_id}/run` | `kyc_ingest` | `data_engineer` (or `service_account`+`data_engineer`) | `auditor`, `compliance_analyst`, `admin` | 401 |

> `data_quality_read` holders per the mapping: `compliance_analyst`,
> `data_engineer`. (`compliance_reviewer` and `admin` do **not** hold it.)

## Behavior guarantees (test-verified)

| Guarantee | Where | Test |
|-----------|-------|------|
| Authorized role allowed | `require_permission` | `test_api_route.py::test_authorized_ingestion_succeeds` |
| Unauthorized role denied (403) | `require_permission` | `test_api_route.py::test_authenticated_without_permission_returns_403` |
| Missing auth denied (401) | `get_current_principal` | `test_phase10_negative_security.py::test_neg_anonymous_denied_on_protected_endpoint` |
| Unknown role → no access | `resolve_permissions` | `test_rbac.py::test_unknown_role_grants_nothing` |
| No role escalation via API input | token contents ignored; principal re-resolved server-side | `test_auth_api.py` (token cannot elevate) |
| Denial is audited | `authorization.denied` event | `test_phase10_acceptance.py::test_e2e_authorization_denial_correlated_and_safe` |
| Safe actor id in audit, no JWT/Principal dump | audit event | same test (asserts `actor_id`, `resource_id`, JWT absent) |

## 401 vs 403

`require_permission` depends on `get_current_principal`, so the split is
automatic and correct: **no/invalid credential → 401** (from the auth
dependency), **authenticated but lacking the permission → 403** (from the
authorization dependency). Both fail closed.
