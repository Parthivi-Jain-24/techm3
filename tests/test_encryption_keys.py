"""Phase 6 tests: AES-256 key validation + key-provider resolution."""

from __future__ import annotations

import base64

import pytest

from app.encryption.errors import EncryptionConfigurationError, InvalidEncryptionKeyError
from app.encryption.keys import AES_256_KEY_SIZE_BYTES, decode_key, resolve_key
from app.secrets.provider import EnvironmentSecretProvider
from tests._encryption_helpers import random_key_b64


# --- key length / format validation (1-6) --------------------------------- #
def test_valid_32_byte_key_accepted() -> None:  # 1
    raw = decode_key(random_key_b64(32))
    assert len(raw) == AES_256_KEY_SIZE_BYTES == 32


def test_16_byte_key_rejected() -> None:  # 2
    with pytest.raises(InvalidEncryptionKeyError):
        decode_key(random_key_b64(16))


def test_24_byte_key_rejected() -> None:  # 3
    with pytest.raises(InvalidEncryptionKeyError):
        decode_key(random_key_b64(24))


def test_empty_key_rejected() -> None:  # 4
    with pytest.raises(InvalidEncryptionKeyError):
        decode_key("")


def test_malformed_base64_key_rejected() -> None:  # 5
    with pytest.raises(InvalidEncryptionKeyError):
        decode_key("not-valid-base64!!!")


def test_plaintext_password_not_silently_accepted_as_key() -> None:  # 6
    # A human password is not 32 raw bytes when base64-decoded (and often
    # isn't even valid base64) -> must be rejected, never silently used.
    with pytest.raises(InvalidEncryptionKeyError):
        decode_key(base64.b64encode(b"my-secret-password").decode())


# --- provider resolution (7, 30-34) ---------------------------------------- #
def test_missing_key_is_safe_configuration_error() -> None:  # 7
    provider = EnvironmentSecretProvider({})
    with pytest.raises(EncryptionConfigurationError):
        resolve_key(provider, "nonexistent-key-id")


def test_service_resolves_key_through_provider_abstraction() -> None:  # 30, 34
    key_b64 = random_key_b64()
    provider = EnvironmentSecretProvider({"my-key": key_b64})
    resolved = resolve_key(provider, "my-key")
    assert resolved == base64.b64decode(key_b64)


def test_no_scattered_os_environ_access() -> None:  # 31
    # Neither module reads os.environ directly (only via the SecretProvider
    # boundary); os.urandom in service.py for nonces is fine and expected.
    import inspect

    import app.encryption.keys as keys_mod
    import app.encryption.service as service_mod

    for mod in (keys_mod, service_mod):
        src = inspect.getsource(mod)
        assert "os.environ.get(" not in src
        assert "os.environ[" not in src


def test_unknown_key_id_fails_safely() -> None:  # 32
    provider = EnvironmentSecretProvider({"known-key": random_key_b64()})
    with pytest.raises(EncryptionConfigurationError):
        resolve_key(provider, "unknown-key-id")


def test_key_material_not_in_error_messages() -> None:  # 33
    key_b64 = random_key_b64()
    provider = EnvironmentSecretProvider({"my-key": key_b64})
    try:
        resolve_key(provider, "missing-key-id")
    except EncryptionConfigurationError as e:
        assert key_b64 not in str(e)

    try:
        decode_key("short")
    except InvalidEncryptionKeyError as e:
        assert "short" not in str(e)
