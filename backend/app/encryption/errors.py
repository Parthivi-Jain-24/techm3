"""Typed error taxonomy for encryption at rest.

Messages are safe by construction: never include key material, plaintext,
decrypted content, or full ciphertext.
"""

from __future__ import annotations


class EncryptionError(Exception):
    """Base class for all encryption-at-rest errors."""


class EncryptionConfigurationError(EncryptionError):
    """Key/provider configuration is missing or unusable."""


class InvalidEncryptionKeyError(EncryptionError):
    """Resolved key material is not a valid 256-bit AES key."""


class UnsupportedEnvelopeVersionError(EncryptionError):
    """The envelope declares an envelope version we do not support."""


class UnsupportedAlgorithmError(EncryptionError):
    """The envelope declares an algorithm we do not support."""


class MalformedEncryptedEnvelopeError(EncryptionError):
    """The envelope is missing required fields or has invalid encoding."""


class EncryptionOperationError(EncryptionError):
    """The underlying AEAD encryption operation failed."""


class DecryptionFailedError(EncryptionError):
    """Authenticated decryption failed (wrong key, tampering, or corruption).

    Deliberately generic: callers must not be able to distinguish "wrong key"
    from "tampered ciphertext" from "tampered nonce" via this exception.
    """


class EncryptedArtifactPathError(EncryptionError):
    """A requested artifact path is outside the approved encrypted directory,
    or otherwise unsafe (traversal, symlink escape, malformed name)."""
