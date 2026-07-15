"""FastAPI authorization dependencies (RBAC enforcement).

``require_permission`` depends on ``get_current_principal`` so the 401-vs-403
distinction is automatic: no/!invalid auth -> 401 (from the auth dependency),
authenticated-but-unauthorized -> 403 here. Fails closed.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

from fastapi import Depends, HTTPException, status

from app.audit.events.actions import AUTHORIZATION_ALLOWED, AUTHORIZATION_DENIED
from app.audit.events.enums import EventType, Outcome, Severity
from app.audit.events.models import Resource
from app.audit.events.resources import PERMISSION
from app.audit.middleware.context import actor_from_principal
from app.audit.service import get_audit_service
from app.identity.authentication.dependencies import get_current_principal
from app.identity.authentication.models import Principal
from app.identity.authorization.permissions import Permission
from app.identity.authorization.policies import has_permission

_FORBIDDEN = HTTPException(
    status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
)


def _audit_authorization(principal: Principal, permission_label: str, *, allowed: bool) -> None:
    # Centralized here (not scattered per-route) -- this dependency IS the
    # single RBAC enforcement seam (PART H: "Do not scatter duplicate RBAC
    # logic across endpoints"); auditing lives at that same seam and never
    # re-derives the allow/deny decision itself, only records it.
    get_audit_service().emit(
        event_type=EventType.AUTHORIZATION,
        action=AUTHORIZATION_ALLOWED if allowed else AUTHORIZATION_DENIED,
        outcome=Outcome.SUCCESS if allowed else Outcome.DENIED,
        severity=Severity.INFO if allowed else Severity.WARNING,
        actor=actor_from_principal(principal),
        resource=Resource(resource_type=PERMISSION, resource_id=permission_label),
    )


def require_permission(permission: Permission) -> Callable[[Principal], Principal]:
    """Dependency factory enforcing a single permission."""

    def _dependency(
        principal: Principal = Depends(get_current_principal),
    ) -> Principal:
        allowed = has_permission(principal, permission)
        _audit_authorization(principal, permission.value, allowed=allowed)
        if not allowed:
            raise _FORBIDDEN
        return principal

    return _dependency


def require_permissions(
    *permissions: Permission, require_all: bool = True
) -> Callable[[Principal], Principal]:
    """Dependency factory enforcing several permissions (all, or any)."""

    required: tuple[Permission, ...] = tuple(permissions)
    label = "+".join(p.value for p in required) if required else "none"

    def _dependency(
        principal: Principal = Depends(get_current_principal),
    ) -> Principal:
        checks: Iterable[bool] = (has_permission(principal, p) for p in required)
        ok = all(checks) if require_all else any(has_permission(principal, p) for p in required)
        allowed = bool(required) and ok  # empty policy fails closed
        _audit_authorization(principal, label, allowed=allowed)
        if not allowed:
            raise _FORBIDDEN
        return principal

    return _dependency
