"""Phase 8 tests: VaultSecretProvider — config, auth, retrieval, KV v2, logging.

All tests use a fake in-process client (``tests._vault_helpers``) — no real
Vault server, Docker, or network access required.
"""

from __future__ import annotations

import logging

import hvac.exceptions as hvac_exc
import pytest

from app.secrets.exceptions import (
    SecretAuthenticationError,
    SecretBackendUnavailableError,
    SecretConfigurationError,
)
from app.secrets.vault_provider import VaultSecretProvider
from tests._vault_helpers import FakeVaultClient, make_vault_provider, random_key_b64

SYNTHETIC_SECRET = "SYNTHETIC_VAULT_SECRET_DO_NOT_LOG_987654"
SYNTHETIC_TOKEN = "SYNTHETIC_VAULT_TOKEN_DO_NOT_LOG_abcxyz"


# --- vault configuration (11-15) ------------------------------------------- #
def test_missing_vault_address_fails_safely() -> None:  # 11
    with pytest.raises(SecretConfigurationError):
        VaultSecretProvider(addr="", token="t", client=FakeVaultClient())
    with pytest.raises(SecretConfigurationError):
        VaultSecretProvider(addr=None, token="t", client=FakeVaultClient())


def test_malformed_vault_auth_method_fails_safely() -> None:  # 12
    with pytest.raises(SecretConfigurationError):
        VaultSecretProvider(
            addr="http://127.0.0.1:8200", token="t", auth_method="kubernetes",
            client=FakeVaultClient(),
        )
    with pytest.raises(SecretConfigurationError):
        VaultSecretProvider(
            addr="http://127.0.0.1:8200", token="t", auth_method="",
            client=FakeVaultClient(),
        )


def test_missing_bootstrap_token_fails_safely(monkeypatch) -> None:  # 13
    monkeypatch.delenv("VAULT_TOKEN", raising=False)
    with pytest.raises(SecretConfigurationError):
        VaultSecretProvider(addr="http://127.0.0.1:8200", token=None, client=FakeVaultClient())


def test_vault_token_not_in_configuration_error_messages() -> None:  # 14
    try:
        VaultSecretProvider(addr="", token=SYNTHETIC_TOKEN, client=FakeVaultClient())
    except SecretConfigurationError as e:
        assert SYNTHETIC_TOKEN not in str(e)


def test_secret_values_not_stored_in_settings_model() -> None:  # 15
    from app.core.config import Settings

    fields = set(Settings.model_fields)
    assert "vault_token" not in fields  # bootstrap credential is NOT a Settings field
    assert "encryption_key" not in fields
    assert "api_credential" not in fields


# --- vault authentication (16-19) ------------------------------------------ #
def test_successful_mocked_authentication_accepted() -> None:  # 16
    provider, client = make_vault_provider(data={"k": "v"})
    assert provider.get_secret("k") == "v"
    assert client.kv2.calls  # a call was actually made through the fake client


def test_authentication_failure_translated_safely() -> None:  # 17
    provider, _ = make_vault_provider(exc=hvac_exc.Forbidden("denied"))
    with pytest.raises(SecretAuthenticationError):
        provider.get_secret("kyc-data-key-v1")

    provider2, _ = make_vault_provider(exc=hvac_exc.Unauthorized("bad token"))
    with pytest.raises(SecretAuthenticationError):
        provider2.get_secret("kyc-data-key-v1")


def test_raw_vault_token_not_exposed_on_auth_failure() -> None:  # 18
    provider, _ = make_vault_provider(
        exc=hvac_exc.Forbidden("denied"), token=SYNTHETIC_TOKEN
    )
    try:
        provider.get_secret("kyc-data-key-v1")
        pytest.fail("expected SecretAuthenticationError")
    except SecretAuthenticationError as e:
        assert SYNTHETIC_TOKEN not in str(e)


def test_low_level_vault_response_not_exposed() -> None:  # 19
    provider, _ = make_vault_provider(exc=hvac_exc.Forbidden("full response internals"))
    try:
        provider.get_secret("kyc-data-key-v1")
        pytest.fail("expected SecretAuthenticationError")
    except SecretAuthenticationError as e:
        assert "full response internals" not in str(e)


# --- vault secret retrieval (20-27) ---------------------------------------- #
def test_known_logical_secret_retrieved_successfully() -> None:  # 20
    key = random_key_b64()
    provider, _ = make_vault_provider(data={"kyc-data-key-v1": key})
    assert provider.get_secret("kyc-data-key-v1") == key


def test_missing_secret_fails_safely_returns_none() -> None:  # 21
    provider, _ = make_vault_provider(data={"other-key": "x"})
    assert provider.get_secret("kyc-data-key-v1") is None


def test_empty_secret_value_treated_as_absent() -> None:  # 22
    provider, _ = make_vault_provider(data={"empty-secret": ""})
    assert provider.get_secret("empty-secret") is None


def test_malformed_vault_response_fails_safely() -> None:  # 23
    provider, client = make_vault_provider()
    # Simulate a KV v2 response missing the expected nested "data" shape.
    client.kv2._exc = None
    original_read = client.kv2.read_secret_version
    client.kv2.read_secret_version = lambda **kw: {"unexpected": "shape"}
    with pytest.raises(SecretBackendUnavailableError):
        provider.get_secret("kyc-data-key-v1")


def test_vault_backend_unavailable_fails_safely() -> None:  # 24
    provider, _ = make_vault_provider(exc=ConnectionError("connection refused"))
    with pytest.raises(SecretBackendUnavailableError):
        provider.get_secret("kyc-data-key-v1")


def test_secret_value_returned_only_to_caller() -> None:  # 25
    provider, _ = make_vault_provider(data={"k": SYNTHETIC_SECRET})
    result = provider.get_secret("k")
    assert result == SYNTHETIC_SECRET  # returned directly, not stored elsewhere
    assert not hasattr(provider, "_cache")  # no internal secret-value cache


def test_secret_value_not_logged(caplog) -> None:  # 26
    provider, _ = make_vault_provider(data={"k": SYNTHETIC_SECRET})
    with caplog.at_level(logging.DEBUG):
        provider.get_secret("k")
    blob = " ".join(r.getMessage() for r in caplog.records)
    assert SYNTHETIC_SECRET not in blob


def test_full_vault_response_not_logged(caplog) -> None:  # 27
    provider, _ = make_vault_provider(data={"k": SYNTHETIC_SECRET, "other": "also-secret"})
    with caplog.at_level(logging.DEBUG):
        provider.get_secret("k")
    blob = " ".join(r.getMessage() for r in caplog.records)
    assert "also-secret" not in blob
    assert "metadata" not in blob


# --- KV v2 behavior (28-31) ------------------------------------------------- #
def test_configured_mount_point_used_correctly() -> None:  # 28
    provider, client = make_vault_provider(
        data={"k": "v"}, mount_point="custom-mount"
    )
    provider.get_secret("k")
    assert client.kv2.calls[-1][1] == "custom-mount"


def test_configured_secret_path_used_correctly() -> None:  # 29
    provider, client = make_vault_provider(
        data={"k": "v"}, secret_path="my-app-secrets"
    )
    provider.get_secret("k")
    assert client.kv2.calls[-1][0] == "my-app-secrets"


def test_logical_name_resolves_within_approved_location() -> None:  # 30
    provider, client = make_vault_provider(
        data={"kyc-data-key-v1": "a", "trusted-kyc-provider-token": "b"},
        secret_path="continuous-kyc",
    )
    assert provider.get_secret("kyc-data-key-v1") == "a"
    assert provider.get_secret("trusted-kyc-provider-token") == "b"
    # Both lookups hit the SAME configured path — no per-call path selection.
    assert all(call[0] == "continuous-kyc" for call in client.kv2.calls)


def test_arbitrary_caller_controlled_vault_paths_not_supported() -> None:  # 31
    # get_secret() takes only a logical NAME — there is no parameter (and no
    # code path) through which a caller can supply a Vault mount/path.
    import inspect

    sig = inspect.signature(VaultSecretProvider.get_secret)
    assert list(sig.parameters) == ["self", "logical_name"]
