"""Secret-retrieval boundary (Phase 5, extended in Phase 8).

``SecretProvider`` is the interface every consumer (EncryptionService,
ApiConnector) depends on — never a concrete provider or a Vault client
directly. ``get_secret_provider()`` resolves the CONFIGURED provider
(environment for local development, or a HashiCorp Vault KV v2 mount in Phase
8) via the centralized, fail-closed factory in ``app.secrets.factory``. See
docs/secrets-vault.md.
"""

from app.secrets.exceptions import (
    SecretAuthenticationError,
    SecretBackendUnavailableError,
    SecretConfigurationError,
    SecretNotFoundError,
    SecretProviderError,
    UnsupportedSecretProviderError,
)
from app.secrets.provider import (
    EnvironmentSecretProvider,
    SecretProvider,
    get_secret_provider,
)
from app.secrets.vault_provider import VaultSecretProvider

__all__ = [
    "SecretProvider",
    "EnvironmentSecretProvider",
    "VaultSecretProvider",
    "get_secret_provider",
    "SecretProviderError",
    "SecretNotFoundError",
    "SecretAuthenticationError",
    "SecretBackendUnavailableError",
    "SecretConfigurationError",
    "UnsupportedSecretProviderError",
]
