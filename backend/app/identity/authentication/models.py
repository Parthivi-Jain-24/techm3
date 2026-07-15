"""Canonical authenticated-principal models.

A ``Principal`` is what protected code receives after authentication. It carries
NO password, NO token, and NO customer PII. Permissions are NOT stored here —
they are derived centrally from roles (see authorization.policies).
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from app.identity.rbac.roles import Role


class PrincipalType(str, Enum):
    USER = "user"        # a human operator
    SERVICE = "service"  # a machine-to-machine identity


class Principal(BaseModel):
    """An authenticated caller. Immutable and free of secrets/PII."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    principal_id: str = Field(..., min_length=1, description="Stable identity id.")
    principal_type: PrincipalType = Field(default=PrincipalType.USER)
    roles: list[Role] = Field(default_factory=list)
    is_active: bool = Field(default=True)


class SafePrincipalView(BaseModel):
    """Client-safe projection of a principal (for /security/me).

    Contains only non-sensitive identity/authorization metadata — never a
    password, hash, token, or secret.
    """

    model_config = ConfigDict(extra="forbid")

    principal_id: str
    principal_type: PrincipalType
    roles: list[str]
    permissions: list[str]
    is_active: bool

    @classmethod
    def from_principal(cls, principal: "Principal") -> "SafePrincipalView":
        # Imported here to avoid a module import cycle.
        from app.identity.authorization.policies import resolve_permissions

        perms = sorted(p.value for p in resolve_permissions(principal.roles))
        return cls(
            principal_id=principal.principal_id,
            principal_type=principal.principal_type,
            roles=[r.value for r in principal.roles],
            permissions=perms,
            is_active=principal.is_active,
        )
