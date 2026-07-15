"""Phase 4 tests: roles, permissions, and centralized RBAC resolution."""

from __future__ import annotations

from app.identity.authentication.models import Principal, PrincipalType
from app.identity.authorization.permissions import Permission
from app.identity.authorization.policies import has_permission, resolve_permissions
from app.identity.rbac.mappings import ROLE_PERMISSIONS
from app.identity.rbac.roles import Role


def test_every_role_is_mapped() -> None:  # 34
    for role in Role:
        assert role in ROLE_PERMISSIONS


def test_known_role_resolves_expected_permissions() -> None:  # 35
    perms = resolve_permissions([Role.DATA_ENGINEER])
    assert Permission.KYC_INGEST in perms
    assert Permission.DATA_QUALITY_READ in perms


def test_unknown_role_grants_nothing() -> None:  # 36
    assert resolve_permissions(["not_a_real_role"]) == frozenset()  # type: ignore[list-item]
    assert resolve_permissions([]) == frozenset()


def test_least_privilege_boundaries() -> None:  # 38, 39, 41
    assert Permission.SECURITY_ADMIN not in resolve_permissions([Role.DATA_ENGINEER])
    assert Permission.KYC_INGEST not in resolve_permissions([Role.AUDITOR])
    assert Permission.SECURITY_ADMIN not in resolve_permissions([Role.COMPLIANCE_ANALYST])


def test_service_account_role_grants_nothing_by_itself() -> None:  # 40
    assert resolve_permissions([Role.SERVICE_ACCOUNT]) == frozenset()
    # A service gains capability only via an explicit functional role.
    assert Permission.KYC_INGEST in resolve_permissions(
        [Role.SERVICE_ACCOUNT, Role.DATA_ENGINEER]
    )
    assert Permission.SECURITY_ADMIN not in resolve_permissions(
        [Role.SERVICE_ACCOUNT, Role.DATA_ENGINEER]
    )


def test_admin_is_not_blanket_access() -> None:
    perms = resolve_permissions([Role.ADMIN])
    assert Permission.SECURITY_ADMIN in perms
    # ADMIN is security/config admin, NOT automatic customer-KYC access.
    assert Permission.KYC_READ not in perms
    assert Permission.KYC_VIEW_SENSITIVE not in perms


def test_has_permission_requires_active_principal() -> None:  # 31 (unit)
    active = Principal(principal_id="a", principal_type=PrincipalType.USER,
                       roles=[Role.DATA_ENGINEER], is_active=True)
    inactive = active.model_copy(update={"is_active": False})
    assert has_permission(active, Permission.KYC_INGEST) is True
    assert has_permission(inactive, Permission.KYC_INGEST) is False


def test_permission_resolution_is_centralized() -> None:  # 37
    # The only source of role->permission truth is ROLE_PERMISSIONS.
    for role in Role:
        assert resolve_permissions([role]) == ROLE_PERMISSIONS[role]


def test_user_and_service_types_are_distinguishable() -> None:  # 33
    assert PrincipalType.USER != PrincipalType.SERVICE
    u = Principal(principal_id="u", principal_type=PrincipalType.USER)
    s = Principal(principal_id="s", principal_type=PrincipalType.SERVICE)
    assert u.principal_type is PrincipalType.USER
    assert s.principal_type is PrincipalType.SERVICE
