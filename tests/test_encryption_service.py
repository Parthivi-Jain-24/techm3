"""Phase 6 tests: AES-256-GCM encryption, decryption, tamper detection."""

from __future__ import annotations

import base64

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.encryption.errors import DecryptionFailedError
from app.encryption.models import NONCE_SIZE_BYTES
from tests._encryption_helpers import make_service, random_key_b64

PLAINTEXT = b'{"synthetic": "SYNTHETIC_TEST_CUSTOMER_987654"}'


# --- encryption (8-13) ----------------------------------------------------- #
def test_plaintext_encrypts_successfully() -> None:  # 8
    svc = make_service()
    envelope = svc.encrypt_bytes(PLAINTEXT, key_id="test-encryption-key", artifact_type="t")
    assert envelope.ciphertext


def test_ciphertext_differs_from_plaintext() -> None:  # 9
    svc = make_service()
    envelope = svc.encrypt_bytes(PLAINTEXT, key_id="test-encryption-key", artifact_type="t")
    assert envelope.ciphertext_bytes != PLAINTEXT
    assert PLAINTEXT not in envelope.ciphertext_bytes


def test_same_plaintext_twice_produces_different_output() -> None:  # 10
    svc = make_service()
    e1 = svc.encrypt_bytes(PLAINTEXT, key_id="test-encryption-key", artifact_type="t")
    e2 = svc.encrypt_bytes(PLAINTEXT, key_id="test-encryption-key", artifact_type="t")
    assert e1.nonce != e2.nonce
    assert e1.ciphertext != e2.ciphertext
    assert svc.decrypt_bytes(e1) == svc.decrypt_bytes(e2) == PLAINTEXT


def test_nonce_has_expected_secure_length() -> None:  # 11
    svc = make_service()
    envelope = svc.encrypt_bytes(PLAINTEXT, key_id="test-encryption-key", artifact_type="t")
    assert len(envelope.nonce_bytes) == NONCE_SIZE_BYTES == 12


def test_uses_aesgcm_maintained_primitive() -> None:  # 12
    import inspect

    import app.encryption.service as service_mod

    src = inspect.getsource(service_mod)
    assert "AESGCM" in src
    assert "from cryptography" in src


def test_original_plaintext_not_mutated() -> None:  # 13
    svc = make_service()
    original = bytearray(PLAINTEXT)
    frozen = bytes(original)
    svc.encrypt_bytes(bytes(original), key_id="test-encryption-key", artifact_type="t")
    assert bytes(original) == frozen


# --- decryption (14-19) ----------------------------------------------------- #
def test_valid_ciphertext_decrypts_to_original() -> None:  # 14
    svc = make_service()
    envelope = svc.encrypt_bytes(PLAINTEXT, key_id="test-encryption-key", artifact_type="t")
    assert svc.decrypt_bytes(envelope) == PLAINTEXT


def test_wrong_key_fails() -> None:  # 15
    svc = make_service()
    envelope = svc.encrypt_bytes(PLAINTEXT, key_id="test-encryption-key", artifact_type="t")
    other_svc = make_service(key_id="test-encryption-key")  # different random key
    with pytest.raises(DecryptionFailedError):
        other_svc.decrypt_bytes(envelope)


def test_modified_ciphertext_fails() -> None:  # 16 (tamper: ciphertext)
    svc = make_service()
    envelope = svc.encrypt_bytes(PLAINTEXT, key_id="test-encryption-key", artifact_type="t")
    raw = bytearray(envelope.ciphertext_bytes)
    raw[0] ^= 0xFF
    tampered = envelope.model_copy(update={"ciphertext": base64.b64encode(bytes(raw)).decode()})
    with pytest.raises(DecryptionFailedError):
        svc.decrypt_bytes(tampered)


def test_modified_nonce_fails() -> None:  # 17 (tamper: nonce)
    svc = make_service()
    envelope = svc.encrypt_bytes(PLAINTEXT, key_id="test-encryption-key", artifact_type="t")
    raw = bytearray(envelope.nonce_bytes)
    raw[0] ^= 0xFF
    tampered = envelope.model_copy(update={"nonce": base64.b64encode(bytes(raw)).decode()})
    with pytest.raises(DecryptionFailedError):
        svc.decrypt_bytes(tampered)


def test_modified_aad_metadata_fails() -> None:  # 18 (tamper: AAD/artifact_type)
    svc = make_service()
    envelope = svc.encrypt_bytes(PLAINTEXT, key_id="test-encryption-key", artifact_type="original")
    tampered = envelope.model_copy(update={"artifact_type": "different"})
    with pytest.raises(DecryptionFailedError):
        svc.decrypt_bytes(tampered)


def test_authentication_failure_never_returns_partial_plaintext() -> None:  # 19
    svc = make_service()
    envelope = svc.encrypt_bytes(PLAINTEXT, key_id="test-encryption-key", artifact_type="t")
    raw = bytearray(envelope.ciphertext_bytes)
    raw[-1] ^= 0xFF
    tampered = envelope.model_copy(update={"ciphertext": base64.b64encode(bytes(raw)).decode()})
    try:
        result = svc.decrypt_bytes(tampered)
        pytest.fail(f"expected DecryptionFailedError, got plaintext-like result: {result!r}")
    except DecryptionFailedError:
        pass  # no plaintext ever returned to this point


# --- JSON convenience round trip ------------------------------------------- #
def test_encrypt_decrypt_json_round_trip() -> None:
    svc = make_service()
    obj = {"marker": "SYNTHETIC_TEST_CUSTOMER_987654", "n": 42}
    envelope = svc.encrypt_json(obj, key_id="test-encryption-key", artifact_type="t")
    assert svc.decrypt_json(envelope) == obj
    assert b"SYNTHETIC_TEST_CUSTOMER_987654" not in envelope.ciphertext_bytes
