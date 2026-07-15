"""Phase 8 tests: centralized provider selection, fail-closed, no fallback."""

from __future__ import annotations

import os

import pytest

from app.secrets.exceptions import (
    SecretBackendUnavailableError,
    SecretConfigurationError,
    UnsupportedSecretProviderError,
)
from app.secrets.factory import (
    SUPPORTED_PROVIDERS,
    reset_provider_cache,
    resolve_secret_provider,
)
from app.secrets.provider import EnvironmentSecretProvider
from app.secrets.vault_provider import VaultSecretProvider
from tests._vault_helpers import FakeVaultClient


@pytest.fixture(autouse=True)
def _reset_cache():
    reset_provider_cache()
    yield
    reset_provider_cache()


# --- provider selection (1-5) --------------------------------------------- #
def test_environment_provider_selected_when_configured() -> None:  # 1
    provider = resolve_secret_provider("environment")
    assert isinstance(provider, EnvironmentSecretProvider)


def test_vault_provider_selected_when_configured(monkeypatch) -> None:  # 2
    monkeypatch.setenv("VAULT_TOKEN", "fake-token")
    from app.core.config import settings

    monkeypatch.setattr(settings, "vault_addr", "http://127.0.0.1:8200")
    provider = resolve_secret_provider("vault")
    assert isinstance(provider, VaultSecretProvider)


def test_unsupported_provider_name_rejected() -> None:  # 3
    with pytest.raises(UnsupportedSecretProviderError):
        resolve_secret_provider("some-random-thing")
    with pytest.raises(UnsupportedSecretProviderError):
        resolve_secret_provider("")


def test_provider_selection_is_centralized() -> None:  # 4
    from app.secrets.provider import get_secret_provider

    # get_secret_provider() (the Phase 5/6 call-site import) must delegate to
    # the SAME centralized factory function, not duplicate selection logic.
    import inspect

    src = inspect.getsource(get_secret_provider)
    assert "resolve_secret_provider" in src


def test_vault_mode_does_not_silently_fall_back_to_environment(monkeypatch) -> None:  # 5, no-fallback
    """SECURITY TEST: vault mode + unavailable Vault + an equivalent secret
    ALSO present in the environment must still FAIL — never silently read the
    environment value instead."""
    monkeypatch.setenv("VAULT_TOKEN", "bootstrap-token")
    monkeypatch.setenv("kyc-data-key-v1", "THIS-MUST-NEVER-BE-USED-AS-FALLBACK")
    from app.core.config import settings

    monkeypatch.setattr(settings, "vault_addr", "http://127.0.0.1:1")  # nothing listens

    provider = resolve_secret_provider("vault")
    assert isinstance(provider, VaultSecretProvider)
    with pytest.raises(SecretBackendUnavailableError):
        provider.get_secret("kyc-data-key-v1")
    # (implicitly) if it had fallen back, this would have returned the
    # planted environment string instead of raising.


def test_supported_providers_are_exactly_environment_and_vault() -> None:
    assert SUPPORTED_PROVIDERS == frozenset({"environment", "vault"})
