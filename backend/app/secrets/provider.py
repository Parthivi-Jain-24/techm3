"""Secret-provider abstraction + a local environment implementation.

A ``SecretProvider`` maps a LOGICAL secret name (e.g. ``KYC_PROVIDER_API_TOKEN``)
to its value. Source configuration references secrets by name only; actual
values live in the environment (local development) or a HashiCorp Vault KV v2
mount (Phase 8 — see ``app.secrets.vault_provider``). Secret values are never
logged and never stored in configuration objects.

``EnvironmentSecretProvider`` is the LOCAL DEVELOPMENT provider — it is not a
production secrets-management system. See docs/secrets-vault.md.
"""

from __future__ import annotations

import os
from typing import Mapping, Protocol


class SecretProvider(Protocol):
    def get_secret(self, logical_name: str) -> str | None:
        """Return the secret value for a logical name, or None if absent."""
        ...


class EnvironmentSecretProvider:
    """Resolves logical secret names from environment variables.

    An optional in-memory ``mapping`` overrides the environment (used by tests so
    no real environment secrets are required).
    """

    def __init__(self, mapping: Mapping[str, str] | None = None) -> None:
        self._mapping = dict(mapping) if mapping is not None else None

    def get_secret(self, logical_name: str) -> str | None:
        if not logical_name:
            return None
        if self._mapping is not None:
            value = self._mapping.get(logical_name)
        else:
            value = os.environ.get(logical_name)
        return value or None


def get_secret_provider() -> SecretProvider:
    """Return the CONFIGURED SecretProvider (Phase 8: environment or vault).

    Delegates to the centralized ``app.secrets.factory`` selector — this
    function's signature and import path are unchanged since Phase 5, so
    existing call sites (``EncryptionService``, ``ApiConnector``) require no
    changes. Selection is explicit and fails closed; see
    ``app.secrets.factory.resolve_secret_provider`` for details (no silent
    fallback from vault to environment).
    """
    from app.secrets.factory import resolve_secret_provider

    return resolve_secret_provider()
