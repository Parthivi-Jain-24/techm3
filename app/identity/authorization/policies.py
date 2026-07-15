"""Centralized authorization logic: permission resolution + privacy-context
selection. This is the ONLY place permissions are computed from roles.
"""

from __future__ import annotations

from collections.abc import Iterable

from app.identity.authorization.permissions import Permission
from app.identity.rbac.mappings import ROLE_PERMISSIONS
from app.identity.rbac.roles import Role
from app.privacy.contexts import ProcessingContext


def resolve_permissions(roles: Iterable[Role]) -> frozenset[Permission]:
    """Union of permissions granted by the given roles.

    Fails closed: unknown roles (or non-Role values) contribute NOTHING, so a
    stray/unmapped role can never grant implicit access.
    """
    granted: set[Permission] = set()
    for role in roles:
        perms = ROLE_PERMISSIONS.get(role) if isinstance(role, Role) else None
        if perms:
            granted |= perms
    return frozenset(granted)


def has_permission(principal, permission: Permission) -> bool:
    """True only if the principal is active AND its roles grant ``permission``."""
    if not getattr(principal, "is_active", False):
        return False
    return permission in resolve_permissions(principal.roles)


def kyc_context_for(principal) -> ProcessingContext:
    """Select the Phase 3 privacy context appropriate to a principal's rights.

    This chooses WHICH representation is appropriate; the actual masking/
    minimization is done by the privacy layer (not duplicated here).

    * ``KYC_VIEW_SENSITIVE`` -> INTERNAL_PROCESSING (the un-minimized view is the
      whole point of the elevated permission).
    * ``KYC_READ`` only      -> HUMAN_REVIEW (identity masked; minimization NOT
      bypassed just because the caller may read KYC).
    """
    perms = resolve_permissions(principal.roles)
    if Permission.KYC_VIEW_SENSITIVE in perms:
        return ProcessingContext.INTERNAL_PROCESSING
    return ProcessingContext.HUMAN_REVIEW
