"""Phase 8 tests: AES-256-GCM (Phase 6) integration with VaultSecretProvider.

Proves the existing EncryptionService works unmodified with a secret resolved
through Vault, using a fake in-process client — no real Vault server needed.
"""

from __future__ import annotations

import inspect
import logging

import pytest

from app.encryption.errors import InvalidEncryptionKeyError
from app.encryption.models import EncryptedEnvelope
from app.encryption.service import EncryptionService
from app.secrets.provider import EnvironmentSecretProvider
from tests._vault_helpers import make_vault_provider, random_key_b64

SYNTHETIC_KEY_MARKER_PLAINTEXT = b'{"synthetic": "SYNTHETIC_TEST_CUSTOMER_987654"}'


def test_existing_service_works_with_environment_provider() -> None:  # 32
    key_b64 = random_key_b64()
    svc = EncryptionService(EnvironmentSecretProvider({"kyc-data-key-v1": key_b64}))
    envelope = svc.encrypt_bytes(b"x", key_id="kyc-data-key-v1", artifact_type="t")
    assert svc.decrypt_bytes(envelope) == b"x"


def test_existing_service_works_with_vault_provider_mocked() -> None:  # 33
    key_b64 = random_key_b64()
    vault_provider, _ = make_vault_provider(data={"kyc-data-key-v1": key_b64})
    svc = EncryptionService(vault_provider)
    envelope = svc.encrypt_bytes(b"x", key_id="kyc-data-key-v1", artifact_type="t")
    assert svc.decrypt_bytes(envelope) == b"x"


def test_same_encryption_service_api_for_both_providers() -> None:  # 34
    key_b64 = random_key_b64()
    env_svc = EncryptionService(EnvironmentSecretProvider({"k": key_b64}))
    vault_provider, _ = make_vault_provider(data={"k": key_b64})
    vault_svc = EncryptionService(vault_provider)

    # Identical API surface, identical behavior, different provider underneath.
    e1 = env_svc.encrypt_bytes(b"same-input", key_id="k", artifact_type="t")
    e2 = vault_svc.encrypt_bytes(b"same-input", key_id="k", artifact_type="t")
    assert env_svc.decrypt_bytes(e1) == vault_svc.decrypt_bytes(e2) == b"same-input"


def test_encryption_service_does_not_depend_on_vault_client() -> None:  # 35
    # Check for actual coupling (imports / instantiation), not prose that
    # merely (correctly) documents the provider-swap design in a docstring.
    import app.encryption.service as service_mod

    src = inspect.getsource(service_mod)
    assert "hvac" not in src
    assert "VaultSecretProvider(" not in src  # never directly instantiated here
    assert "from app.secrets.vault_provider" not in src


def test_valid_vault_key_encrypts_successfully() -> None:  # 36
    key_b64 = random_key_b64()
    vault_provider, _ = make_vault_provider(data={"kyc-data-key-v1": key_b64})
    svc = EncryptionService(vault_provider)
    envelope = svc.encrypt_bytes(
        SYNTHETIC_KEY_MARKER_PLAINTEXT, key_id="kyc-data-key-v1", artifact_type="demo"
    )
    assert isinstance(envelope, EncryptedEnvelope)
    assert envelope.ciphertext


def test_vault_encrypted_content_decrypts_successfully() -> None:  # 37
    key_b64 = random_key_b64()
    vault_provider, _ = make_vault_provider(data={"kyc-data-key-v1": key_b64})
    svc = EncryptionService(vault_provider)
    envelope = svc.encrypt_bytes(
        SYNTHETIC_KEY_MARKER_PLAINTEXT, key_id="kyc-data-key-v1", artifact_type="demo"
    )
    assert svc.decrypt_bytes(envelope) == SYNTHETIC_KEY_MARKER_PLAINTEXT


def test_invalid_vault_key_material_rejected_by_existing_validation() -> None:  # 38
    # 16 bytes (AES-128-sized), not 32 -> existing Phase 6 key.decode_key() must reject.
    bad_key_b64 = random_key_b64(n_bytes=16)
    vault_provider, _ = make_vault_provider(data={"bad-key": bad_key_b64})
    svc = EncryptionService(vault_provider)
    with pytest.raises(InvalidEncryptionKeyError):
        svc.encrypt_bytes(b"x", key_id="bad-key", artifact_type="t")


def test_vault_resolved_key_value_not_logged(caplog) -> None:  # 39
    key_b64 = random_key_b64()
    vault_provider, _ = make_vault_provider(data={"kyc-data-key-v1": key_b64})
    svc = EncryptionService(vault_provider)
    with caplog.at_level(logging.DEBUG):
        envelope = svc.encrypt_bytes(b"x", key_id="kyc-data-key-v1", artifact_type="t")
        svc.decrypt_bytes(envelope)
    blob = " ".join(r.getMessage() for r in caplog.records)
    assert key_b64 not in blob


def test_key_value_not_stored_in_encrypted_envelope() -> None:  # 40
    key_b64 = random_key_b64()
    vault_provider, _ = make_vault_provider(data={"kyc-data-key-v1": key_b64})
    svc = EncryptionService(vault_provider)
    envelope = svc.encrypt_bytes(
        SYNTHETIC_KEY_MARKER_PLAINTEXT, key_id="kyc-data-key-v1", artifact_type="demo"
    )
    dumped = envelope.model_dump_json()
    assert key_b64 not in dumped
    assert "key_material" not in dumped
    assert envelope.key_id == "kyc-data-key-v1"  # reference only, never the key
