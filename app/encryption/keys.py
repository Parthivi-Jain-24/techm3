"""AES-256 key resolution through the Phase 5 SecretProvider boundary.

The encryption service asks for a key by logical ``key_id`` (e.g.
``"kyc-data-key-v1"``); this module resolves it via ``SecretProvider`` and
strictly validates it decodes to exactly 32 bytes (256 bits). It never touches
``os.environ`` directly and never logs key material.

Swapping ``EnvironmentSecretProvider`` for a future ``VaultSecretProvider``
(Phase 8) requires no change here or in ``EncryptionService``.
"""

from __future__ import annotations

import base64
import binascii

from app.audit.integrations import audit_secret_access
from app.encryption.errors import (
    EncryptionConfigurationError,
    InvalidEncryptionKeyError,
)
from app.secrets.provider import SecretProvider

AES_256_KEY_SIZE_BYTES = 32  # 256 bits


def decode_key(key_b64: str) -> bytes:
    """Decode + strictly validate a Base64-encoded AES-256 key.

    Rejects malformed Base64, empty keys, and any length other than exactly 32
    bytes (rejects AES-128/192-sized keys and arbitrary password strings).
    Never truncates or pads.
    """
    if not key_b64 or not key_b64.strip():
        raise InvalidEncryptionKeyError("encryption key is empty")
    try:
        raw = base64.b64decode(key_b64, validate=True)
    except (binascii.Error, ValueError):
        raise InvalidEncryptionKeyError("encryption key is not valid Base64")
    if len(raw) != AES_256_KEY_SIZE_BYTES:
        raise InvalidEncryptionKeyError(
            f"encryption key must decode to {AES_256_KEY_SIZE_BYTES} bytes "
            f"(got {len(raw)})"
        )
    return raw


def resolve_key(provider: SecretProvider, key_id: str) -> bytes:
    """Resolve ``key_id`` -> validated 32-byte key material via the provider.

    Raises ``EncryptionConfigurationError`` if the logical secret is absent,
    ``InvalidEncryptionKeyError`` if present but malformed/wrong length. Never
    includes the key value in any exception message.
    """
    if not key_id:
        raise EncryptionConfigurationError("no key_id specified")
    try:
        secret = provider.get_secret(key_id)
    except Exception:
        audit_secret_access(provider, key_id, success=False)
        raise
    if not secret:
        audit_secret_access(provider, key_id, success=False)
        raise EncryptionConfigurationError(
            f"no key material configured for key_id={key_id!r}"
        )
    audit_secret_access(provider, key_id, success=True)
    return decode_key(secret)
