"""Centralized SecretProvider selection (Phase 8).

The ONLY place ``SECRETS_PROVIDER`` is interpreted. Application code depends
on the ``SecretProvider`` interface (``app.secrets.provider``), never directly
on ``EnvironmentSecretProvider``, ``VaultSecretProvider``, or an ``hvac``
client — this module is the single seam where a mode is chosen.

Fail-closed, no fallback: if ``vault`` is selected and the ``VaultSecretProvider``
cannot be constructed (missing config, missing bootstrap token), this raises —
it never silently returns an ``EnvironmentSecretProvider`` instead. Requesting
an unrecognized provider name also raises rather than defaulting to anything.
"""

from __future__ import annotations

from app.core.config import settings
from app.secrets.exceptions import UnsupportedSecretProviderError
from app.secrets.provider import EnvironmentSecretProvider, SecretProvider

SUPPORTED_PROVIDERS = frozenset({"environment", "vault"})

# Cached singletons so we don't rebuild an EnvironmentSecretProvider or a
# hvac-backed VaultSecretProvider (network client) on every secret lookup.
# Not a secret-VALUE cache — no secret material is stored here, only the
# provider objects themselves (mirrors app.secrets.provider's existing
# `_default_provider` pattern).
_environment_provider = EnvironmentSecretProvider()
_vault_provider: SecretProvider | None = None


def resolve_secret_provider(provider_name: str | None = None) -> SecretProvider:
    """Return the configured ``SecretProvider``. Fails closed; never falls back.

    ``provider_name`` defaults to ``settings.secrets_provider``; tests may pass
    an explicit value to exercise selection logic without touching global state.
    """
    name = (provider_name if provider_name is not None else settings.secrets_provider).strip().lower()

    if name not in SUPPORTED_PROVIDERS:
        raise UnsupportedSecretProviderError(
            f"unsupported SECRETS_PROVIDER: {name!r}; "
            f"expected one of {sorted(SUPPORTED_PROVIDERS)}"
        )

    if name == "environment":
        return _environment_provider

    # name == "vault" — construct (or reuse) a real VaultSecretProvider.
    # Any failure here propagates as-is (SecretConfigurationError etc.) —
    # it is NEVER caught to silently fall back to the environment provider.
    global _vault_provider
    if _vault_provider is None:
        from app.secrets.vault_provider import VaultSecretProvider

        _vault_provider = VaultSecretProvider()
    return _vault_provider


def reset_provider_cache() -> None:
    """Clear the cached Vault provider (test-only helper).

    Lets tests reconfigure Vault settings between cases without a stale
    cached client. Never clears secret VALUES (none are cached here).
    """
    global _vault_provider
    _vault_provider = None
