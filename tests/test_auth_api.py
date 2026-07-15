"""Phase 4 tests: OAuth2 token endpoint, authentication, RBAC via the API."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.identity.authentication.models import Principal, PrincipalType
from app.identity.authentication.tokens import create_access_token
from app.identity.authorization.dependencies import (
    require_permission,
    require_permissions,
)
from app.identity.authorization.permissions import Permission
from app.identity.rbac.roles import Role

SECRET = "unit-test-only-jwt-secret-key-0123456789abcdef"
AUTH = lambda t: {"Authorization": f"Bearer {t}"}  # noqa: E731


# --- token endpoint (7-12) ----------------------------------------------- #
def test_valid_credentials_return_bearer_token(auth_client) -> None:  # 7
    r = auth_client.post("/api/v1/auth/token",
                         data={"username": "engineer", "password": "pw-engineer"})
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "bearer" and body["access_token"]


def test_invalid_password_and_unknown_user_same_generic_failure(auth_client) -> None:  # 8, 9
    bad_pw = auth_client.post("/api/v1/auth/token",
                              data={"username": "engineer", "password": "WRONG"})
    unknown = auth_client.post("/api/v1/auth/token",
                               data={"username": "nobody", "password": "x"})
    assert bad_pw.status_code == unknown.status_code == 401
    assert bad_pw.json()["detail"] == unknown.json()["detail"] == "Invalid credentials"


def test_inactive_principal_cannot_get_token(auth_client) -> None:  # 10
    r = auth_client.post("/api/v1/auth/token",
                         data={"username": "ghost", "password": "pw-ghost"})
    assert r.status_code == 401


def test_token_response_has_no_hash_or_secret(auth_client) -> None:  # 11, 12
    r = auth_client.post("/api/v1/auth/token",
                         data={"username": "engineer", "password": "pw-engineer"})
    text = r.text.lower()
    assert "argon2" not in text and "password" not in text and SECRET not in r.text


# --- authentication (27-32) ---------------------------------------------- #
def test_protected_without_token_is_401(auth_client) -> None:  # 27, 44
    assert auth_client.get("/api/v1/security/me").status_code == 401


def test_invalid_token_is_401(auth_client) -> None:  # 28
    assert auth_client.get("/api/v1/security/me", headers=AUTH("garbage")).status_code == 401


def test_expired_token_is_401(auth_client) -> None:  # 29
    past = datetime.now(timezone.utc) - timedelta(minutes=30)
    p = Principal(principal_id="U-ENGINEER", principal_type=PrincipalType.USER,
                  roles=[Role.DATA_ENGINEER])
    token = create_access_token(p, secret=SECRET, now=past, expires_minutes=1)
    assert auth_client.get("/api/v1/security/me", headers=AUTH(token)).status_code == 401


def test_valid_token_resolves_principal(auth_client) -> None:  # 30
    tok = auth_client.token_for("engineer", "pw-engineer")
    r = auth_client.get("/api/v1/security/me", headers=AUTH(tok))
    assert r.status_code == 200
    assert r.json()["principal_id"] == "U-ENGINEER"


def test_unknown_principal_rejected(auth_client) -> None:  # 32
    ghost = Principal(principal_id="U-DOES-NOT-EXIST", principal_type=PrincipalType.USER,
                      roles=[Role.DATA_ENGINEER])
    token = create_access_token(ghost, secret=SECRET)
    assert auth_client.get("/api/v1/security/me", headers=AUTH(token)).status_code == 401


def test_deactivated_principal_rejected_after_token_issued(auth_client) -> None:  # 31
    # A token minted for the inactive user's id must still be rejected.
    token = create_access_token(
        Principal(principal_id="U-GHOST", principal_type=PrincipalType.USER,
                  roles=[Role.COMPLIANCE_ANALYST]),
        secret=SECRET,
    )
    assert auth_client.get("/api/v1/security/me", headers=AUTH(token)).status_code == 401


# --- authorization (42, 43, 46, 55) -------------------------------------- #
def test_permission_granted_succeeds(auth_client) -> None:  # 42, 55
    tok = auth_client.token_for("engineer", "pw-engineer")  # has DATA_QUALITY_READ
    r = auth_client.get("/api/v1/security/data-quality-access-check", headers=AUTH(tok))
    assert r.status_code == 200 and r.json()["status"] == "authorized"


def test_permission_missing_is_403(auth_client) -> None:  # 43
    tok = auth_client.token_for("auditor", "pw-auditor")  # no DATA_QUALITY_READ
    r = auth_client.get("/api/v1/security/data-quality-access-check", headers=AUTH(tok))
    assert r.status_code == 403


def test_client_supplied_role_header_is_ignored(auth_client) -> None:  # 46
    tok = auth_client.token_for("auditor", "pw-auditor")
    headers = {**AUTH(tok), "X-Role": "admin", "X-Roles": "data_engineer"}
    r = auth_client.get("/api/v1/security/data-quality-access-check", headers=headers)
    assert r.status_code == 403  # spoofed headers grant nothing


def test_service_identity_uses_functional_role(auth_client) -> None:  # 33 (api), service
    tok = auth_client.token_for("svc", "pw-svc")  # SERVICE_ACCOUNT + DATA_ENGINEER
    me = auth_client.get("/api/v1/security/me", headers=AUTH(tok)).json()
    assert me["principal_type"] == "service"
    assert "data_quality_read" in me["permissions"]
    assert "security_admin" not in me["permissions"]


# --- empty policy fails closed (45) -------------------------------------- #
def test_empty_permission_policy_fails_closed() -> None:  # 45
    dep = require_permissions()  # no permissions specified
    principal = Principal(principal_id="x", roles=[Role.ADMIN])
    import fastapi
    with pytest.raises(fastapi.HTTPException) as exc:
        dep(principal)
    assert exc.value.status_code == 403


def test_require_permission_denies_without_permission() -> None:
    dep = require_permission(Permission.SECURITY_ADMIN)
    principal = Principal(principal_id="x", roles=[Role.DATA_ENGINEER])
    import fastapi
    with pytest.raises(fastapi.HTTPException) as exc:
        dep(principal)
    assert exc.value.status_code == 403


# --- API safety (51-54, 56) ---------------------------------------------- #
def test_health_remains_public(auth_client) -> None:  # 51
    r = auth_client.get("/api/v1/health/live")
    assert r.status_code == 200 and r.json() == {"status": "alive"}


def test_me_requires_auth(auth_client) -> None:  # 52
    assert auth_client.get("/api/v1/security/me").status_code == 401


def test_me_exposes_no_secrets_or_hashes(auth_client) -> None:  # 53, 54
    tok = auth_client.token_for("analyst", "pw-analyst")
    body = auth_client.get("/api/v1/security/me", headers=AUTH(tok)).text.lower()
    for banned in ("argon2", "password", "secret", "access_token", "jwt"):
        assert banned not in body


def test_security_headers_present(auth_client) -> None:  # 56
    h = auth_client.get("/api/v1/health/live").headers
    assert h.get("X-Content-Type-Options") == "nosniff"
    assert h.get("X-Frame-Options") == "DENY"
    assert h.get("Referrer-Policy") == "no-referrer"
