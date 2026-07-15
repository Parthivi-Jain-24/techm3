"""Versioned encrypted-envelope model.

The envelope is the ONLY thing that ever touches disk for an encrypted
artifact. It carries a non-secret ``key_id`` (never key material), the random
nonce (not secret — safe to store alongside ciphertext), and the ciphertext
(which includes the GCM authentication tag, per the ``cryptography`` AESGCM
API). Strict validation rejects unknown versions/algorithms and malformed
Base64 so a corrupted or forged envelope fails safely before any crypto runs.
"""

from __future__ import annotations

import base64
import binascii
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.encryption.errors import (
    MalformedEncryptedEnvelopeError,
    UnsupportedAlgorithmError,
    UnsupportedEnvelopeVersionError,
)
from app.schemas.common import utcnow

ENVELOPE_VERSION = 1
ALGORITHM = "AES-256-GCM"
NONCE_SIZE_BYTES = 12  # 96-bit, the standard/recommended AES-GCM nonce size


def _b64_decode(field_name: str, value: str) -> bytes:
    try:
        return base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError):
        raise MalformedEncryptedEnvelopeError(f"{field_name} is not valid Base64")


class EncryptedEnvelope(BaseModel):
    """On-disk / stored representation of one encrypted artifact.

    Contains NO plaintext and NO encryption key material — only the non-secret
    ``key_id`` reference, nonce, and ciphertext (Base64-encoded for safe JSON
    storage).
    """

    model_config = ConfigDict(extra="forbid")

    version: int = Field(..., description="Envelope format version.")
    algorithm: str = Field(..., description="Fixed AEAD algorithm identifier.")
    key_id: str = Field(..., min_length=1, description="Non-secret key reference.")
    artifact_type: str = Field(..., min_length=1, description="Logical content type (AAD).")
    nonce: str = Field(..., description="Base64-encoded 12-byte GCM nonce.")
    ciphertext: str = Field(..., description="Base64-encoded ciphertext (incl. GCM tag).")
    created_at: datetime = Field(default_factory=utcnow)

    @field_validator("version")
    @classmethod
    def _check_version(cls, v: int) -> int:
        if v != ENVELOPE_VERSION:
            raise UnsupportedEnvelopeVersionError(f"unsupported envelope version: {v}")
        return v

    @field_validator("algorithm")
    @classmethod
    def _check_algorithm(cls, v: str) -> str:
        if v != ALGORITHM:
            raise UnsupportedAlgorithmError(f"unsupported algorithm: {v!r}")
        return v

    @field_validator("nonce")
    @classmethod
    def _check_nonce(cls, v: str) -> str:
        raw = _b64_decode("nonce", v)
        if len(raw) != NONCE_SIZE_BYTES:
            raise MalformedEncryptedEnvelopeError(
                f"nonce must decode to {NONCE_SIZE_BYTES} bytes"
            )
        return v

    @field_validator("ciphertext")
    @classmethod
    def _check_ciphertext(cls, v: str) -> str:
        raw = _b64_decode("ciphertext", v)
        if len(raw) == 0:
            raise MalformedEncryptedEnvelopeError("ciphertext must not be empty")
        return v

    @property
    def nonce_bytes(self) -> bytes:
        return base64.b64decode(self.nonce, validate=True)

    @property
    def ciphertext_bytes(self) -> bytes:
        return base64.b64decode(self.ciphertext, validate=True)

    def aad_bytes(self) -> bytes:
        """Canonical AAD encoding — MUST match between encrypt and decrypt."""
        return build_aad(self.version, self.algorithm, self.artifact_type)


def build_aad(version: int, algorithm: str, artifact_type: str) -> bytes:
    """Centralized, deterministic AAD encoding (version|algorithm|artifact_type).

    Authenticates stable envelope metadata so tampering with version/algorithm/
    artifact_type is detected, without embedding anything secret or unstable.
    """
    return f"{version}|{algorithm}|{artifact_type}".encode("utf-8")
