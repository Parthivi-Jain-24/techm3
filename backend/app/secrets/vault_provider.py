"""HashiCorp Vault-backed SecretProvider (KV secrets engine v2).

``VaultSecretProvider`` retrieves application secrets from ONE configured
Vault KV v2 mount/path, translating low-level Vault/hvac errors into the safe
``app.secrets.exceptions`` taxonomy. It implements the exact same
``get_secret(logical_name) -> str | None`` contract as
``EnvironmentSecretProvider`` (``None`` = "not configured") — this is why
Phase 5's ``ApiConnector`` and Phase 6's ``resolve_key``/``EncryptionService``
need no changes to work with either provider.

Only ``mount_point``/``secret_path`` (server-controlled configuration) are
ever read — callers supply a LOGICAL secret name, never a Vault path. There is
no way for an API caller or ingested data to select an arbitrary Vault
location.

Bootstrap credential note: the Vault TOKEN used to authenticate TO Vault is
read directly from the process environment (``VAULT_TOKEN``), not through a
SecretProvider — that would be circular (the provider can't fetch the
credential needed to construct itself). This is the one deliberate, documented
exception to "secrets go through SecretProvider". See docs/secrets-vault.md.
"""

from __future__ import annotations

import os

from app.core.config import settings
from app.secrets.exceptions import (
    SecretAuthenticationError,
    SecretBackendUnavailableError,
    SecretConfigurationError,
)

SUPPORTED_AUTH_METHODS = frozenset({"token"})


class VaultSecretProvider:
    """Resolves logical secret names from a single approved Vault KV v2 path."""

    def __init__(
        self,
        *,
        addr: str | None = None,
        token: str | None = None,
        mount_point: str | None = None,
        secret_path: str | None = None,
        auth_method: str | None = None,
        client: object | None = None,
    ) -> None:
        self._addr = addr if addr is not None else settings.vault_addr
        self._mount_point = mount_point if mount_point is not None else settings.vault_mount_point
        self._secret_path = secret_path if secret_path is not None else settings.vault_secret_path
        self._auth_method = auth_method if auth_method is not None else settings.vault_auth_method

        if self._auth_method not in SUPPORTED_AUTH_METHODS:
            raise SecretConfigurationError(
                f"unsupported vault auth method: {self._auth_method!r}"
            )
        if not self._addr:
            raise SecretConfigurationError("VAULT_ADDR is not configured")

        # Bootstrap credential — see module docstring. Tests inject `token=`
        # (or `client=`) directly instead of relying on the environment.
        resolved_token = token if token is not None else os.environ.get("VAULT_TOKEN")
        if not resolved_token:
            raise SecretConfigurationError(
                "VAULT_TOKEN bootstrap credential is not configured"
            )

        if client is not None:
            self._client = client
        else:
            import hvac  # local import: only required when Vault mode is actually used

            self._client = hvac.Client(url=self._addr, token=resolved_token)

    def get_secret(self, logical_name: str) -> str | None:
        """Return the secret value for ``logical_name``, or ``None`` if the
        approved Vault path exists but does not contain that key (matching
        ``EnvironmentSecretProvider``'s "not configured" semantics).

        Raises a typed ``SecretProviderError`` subclass for genuine
        infrastructure problems: authentication failure, an unreachable
        backend, or a malformed response. Never returns partial/garbage data.
        """
        if not logical_name:
            return None

        try:
            import hvac.exceptions as hvac_exc
        except ImportError:
            hvac_exc = None

        try:
            response = self._client.secrets.kv.v2.read_secret_version(
                path=self._secret_path,
                mount_point=self._mount_point,
                raise_on_deleted_version=True,
            )
        except Exception as exc:  # noqa: BLE001 - translate ALL backend errors safely
            if hvac_exc is not None and isinstance(
                exc, (hvac_exc.Forbidden, hvac_exc.Unauthorized)
            ):
                raise SecretAuthenticationError("vault authentication failed") from exc
            if hvac_exc is not None and isinstance(exc, hvac_exc.InvalidPath):
                return None  # nothing stored at the configured path yet
            raise SecretBackendUnavailableError("vault backend is unavailable") from exc

        try:
            data = response["data"]["data"]
        except (KeyError, TypeError) as exc:
            raise SecretBackendUnavailableError(
                "vault returned an unexpected response shape"
            ) from exc

        value = data.get(logical_name)
        return value or None
