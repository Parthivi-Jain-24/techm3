"""Safe error taxonomy for secret-provider operations.

Messages are safe by construction: never include secret values, Vault tokens,
API credentials, or full backend responses.
"""

from __future__ import annotations


class SecretProviderError(Exception):
    """Base class for all secret-provider errors."""


class SecretNotFoundError(SecretProviderError):
    """The requested logical secret does not exist at the approved location.

    Reserved for callers/providers that need an explicit "not found" signal
    distinct from ``None``. The built-in providers in this module return
    ``None`` for "not configured" (matching the existing ``SecretProvider``
    contract used throughout Phase 5/6), so this is not raised by them today.
    """


class SecretAuthenticationError(SecretProviderError):
    """The backend rejected the provider's authentication credential."""


class SecretBackendUnavailableError(SecretProviderError):
    """The secrets backend could not be reached, or returned an unusable
    response (malformed shape, unexpected error, etc.)."""


class SecretConfigurationError(SecretProviderError):
    """The provider is missing required configuration (address, bootstrap
    credential, unsupported auth method, etc.)."""


class UnsupportedSecretProviderError(SecretProviderError):
    """The configured ``SECRETS_PROVIDER`` value is not a supported provider."""
