"""Identity provider abstraction + a DEVELOPMENT-ONLY implementation.

There is no persistent identity store in this phase. ``DevelopmentIdentityProvider``
holds in-memory records so authentication logic never depends on scattered
hardcoded dictionaries. In production this is replaced by a database-backed
store or an external OAuth2/OIDC provider WITHOUT changing the auth logic.

Records are configured via the environment (``DEV_AUTH_USERS`` JSON) so no
working credentials are committed. Tests construct their own providers directly.
"""

from __future__ import annotations

import json
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from app.identity.authentication.models import Principal, PrincipalType
from app.identity.authentication.password import dummy_verify, verify_password
from app.identity.rbac.roles import Role


class PrincipalRecord(BaseModel):
    """Internal identity record. The ``password_hash`` NEVER leaves this layer."""

    model_config = ConfigDict(extra="forbid")

    username: str
    principal_id: str
    password_hash: str
    principal_type: PrincipalType = PrincipalType.USER
    roles: list[Role] = Field(default_factory=list)
    is_active: bool = True

    def to_principal(self) -> Principal:
        return Principal(
            principal_id=self.principal_id,
            principal_type=self.principal_type,
            roles=list(self.roles),
            is_active=self.is_active,
        )


class IdentityProvider(Protocol):
    """Trusted source of identity records (auth + resolution)."""

    def authenticate(self, username: str, password: str) -> PrincipalRecord | None: ...
    def get_by_id(self, principal_id: str) -> PrincipalRecord | None: ...


class DevelopmentIdentityProvider:
    """In-memory identity provider for local dev / tests only."""

    def __init__(self, records: list[PrincipalRecord]) -> None:
        self._by_username = {r.username: r for r in records}
        self._by_id = {r.principal_id: r for r in records}

    def authenticate(self, username: str, password: str) -> PrincipalRecord | None:
        record = self._by_username.get(username)
        if record is None:
            dummy_verify(password)  # constant-time-ish: no username enumeration
            return None
        if not verify_password(record.password_hash, password):
            return None
        return record

    def get_by_id(self, principal_id: str) -> PrincipalRecord | None:
        return self._by_id.get(principal_id)


def build_dev_provider_from_config(raw_json: str) -> DevelopmentIdentityProvider:
    """Build a dev provider from a JSON array string (``settings.dev_auth_users``).

    Malformed entries are skipped rather than crashing startup. An empty/blank
    value yields a provider with no users (default-deny).
    """
    records: list[PrincipalRecord] = []
    raw_json = (raw_json or "").strip()
    if raw_json:
        try:
            items = json.loads(raw_json)
        except json.JSONDecodeError:
            items = []
        for item in items if isinstance(items, list) else []:
            try:
                records.append(PrincipalRecord(**item))
            except Exception:  # noqa: BLE001 - skip invalid demo entries safely
                continue
    return DevelopmentIdentityProvider(records)
