"""Minimal service-identity foundation (machine-to-machine).

A service identity is a ``Principal`` with ``principal_type=SERVICE``. It is
distinguishable from human users, holds ONLY the permissions granted by its
explicit functional roles, and never inherits ADMIN implicitly (the
SERVICE_ACCOUNT role grants nothing by itself).

Future production options (NOT implemented here): OAuth2 client-credentials
flow, mTLS, service-mesh identity, cloud workload identity. Designed so future
audit logging can attribute actions to a specific service principal.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.identity.authentication.models import Principal, PrincipalType
from app.identity.rbac.roles import Role


class ServiceIdentity(BaseModel):
    """An explicitly-scoped machine identity."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    principal_id: str = Field(..., min_length=1)
    # SERVICE_ACCOUNT marks it as a service; functional roles grant capabilities.
    roles: list[Role] = Field(default_factory=lambda: [Role.SERVICE_ACCOUNT])
    is_active: bool = True

    def to_principal(self) -> Principal:
        roles = list(self.roles)
        if Role.SERVICE_ACCOUNT not in roles:
            roles.append(Role.SERVICE_ACCOUNT)
        return Principal(
            principal_id=self.principal_id,
            principal_type=PrincipalType.SERVICE,
            roles=roles,
            is_active=self.is_active,
        )
