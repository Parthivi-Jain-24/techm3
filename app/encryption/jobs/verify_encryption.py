"""Safe local demonstration of AES-256-GCM encrypt/decrypt/tamper behavior.

Uses ONLY synthetic demonstration data — never real KYC records. Prints no key
material and no full ciphertext dump. Requires ENCRYPTION_KEY_<id> to be
configured (see docs/encryption-at-rest.md); if absent, a fresh random test
key is generated in-memory for this demonstration run only (never persisted).

Usage (from backend/):
    python -m app.encryption.jobs.verify_encryption
"""

from __future__ import annotations

import base64
import os

from app.encryption.errors import DecryptionFailedError
from app.encryption.service import EncryptionService
from app.secrets.provider import EnvironmentSecretProvider

_DEMO_KEY_ID = "verify-encryption-demo-key"
_SYNTHETIC_PLAINTEXT = b'{"synthetic_customer": "SYNTHETIC_TEST_CUSTOMER_987654"}'


def main() -> None:
    # In-memory random key for this demo run only — never printed, never persisted.
    demo_key_b64 = base64.b64encode(os.urandom(32)).decode("ascii")
    service = EncryptionService(EnvironmentSecretProvider({_DEMO_KEY_ID: demo_key_b64}))

    print("=== AES-256-GCM encryption verification (synthetic data only) ===")

    # 1. Round trip.
    envelope = service.encrypt_bytes(
        _SYNTHETIC_PLAINTEXT, key_id=_DEMO_KEY_ID, artifact_type="demo"
    )
    recovered = service.decrypt_bytes(envelope)
    print(f"round_trip_ok        : {recovered == _SYNTHETIC_PLAINTEXT}")
    print(f"algorithm             : {envelope.algorithm}")
    print(f"envelope_version      : {envelope.version}")
    print(f"key_id                : {envelope.key_id}")
    print(f"nonce_bytes           : {len(envelope.nonce_bytes)}")
    print(f"ciphertext_bytes      : {len(envelope.ciphertext_bytes)}")

    # 2. Fresh-nonce check: same plaintext encrypted twice differs.
    envelope2 = service.encrypt_bytes(
        _SYNTHETIC_PLAINTEXT, key_id=_DEMO_KEY_ID, artifact_type="demo"
    )
    print(f"nonces_differ         : {envelope.nonce != envelope2.nonce}")
    print(f"ciphertexts_differ    : {envelope.ciphertext != envelope2.ciphertext}")
    print(f"second_decrypt_ok     : {service.decrypt_bytes(envelope2) == _SYNTHETIC_PLAINTEXT}")

    # 3. Tamper detection.
    tampered = envelope.model_copy(update={"ciphertext": _flip_last_byte(envelope.ciphertext)})
    try:
        service.decrypt_bytes(tampered)
        print("tamper_detected       : FAIL (no exception raised)")
    except DecryptionFailedError:
        print("tamper_detected       : True")

    # 4. Wrong key.
    other_key_b64 = base64.b64encode(os.urandom(32)).decode("ascii")
    other_service = EncryptionService(
        EnvironmentSecretProvider({_DEMO_KEY_ID: other_key_b64})
    )
    try:
        other_service.decrypt_bytes(envelope)
        print("wrong_key_rejected    : FAIL (no exception raised)")
    except DecryptionFailedError:
        print("wrong_key_rejected    : True")


def _flip_last_byte(b64_value: str) -> str:
    raw = bytearray(base64.b64decode(b64_value))
    raw[-1] ^= 0xFF
    return base64.b64encode(bytes(raw)).decode("ascii")


if __name__ == "__main__":
    main()
