"""AES-256-GCM encryption service.

Uses the maintained, vetted AEAD primitive
``cryptography.hazmat.primitives.ciphers.aead.AESGCM`` — no hand-rolled AES/GCM,
no manual tag handling (the library returns ciphertext-with-tag as one blob).

Every operation is explicit (no encryption on import), generates a fresh
cryptographically random 96-bit nonce internally (callers cannot supply one),
never logs key material or plaintext, and never mutates caller-provided bytes.
"""

from __future__ import annotations

import base64
import json
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.audit.events.actions import (
    ENCRYPTION_DECRYPT_FAILED,
    ENCRYPTION_DECRYPT_SUCCEEDED,
    ENCRYPTION_ENCRYPT_FAILED,
    ENCRYPTION_ENCRYPT_SUCCEEDED,
)
from app.audit.events.enums import EventType, Outcome, Severity
from app.audit.events.models import Resource
from app.audit.events.resources import ENCRYPTED_ARTIFACT
from app.audit.service import get_audit_service
from app.encryption.errors import (
    DecryptionFailedError,
    EncryptionOperationError,
)
from app.encryption.keys import resolve_key
from app.encryption.models import ALGORITHM, ENVELOPE_VERSION, EncryptedEnvelope, build_aad
from app.secrets.provider import SecretProvider, get_secret_provider


class EncryptionService:
    """Encrypts/decrypts bytes as versioned AES-256-GCM envelopes."""

    def __init__(self, secret_provider: SecretProvider) -> None:
        self._secrets = secret_provider

    def encrypt_bytes(
        self, plaintext: bytes, *, key_id: str, artifact_type: str
    ) -> EncryptedEnvelope:
        """Encrypt ``plaintext`` under ``key_id`` and return a signed envelope.

        A fresh random 96-bit nonce is generated for this call only. AAD binds
        (version, algorithm, artifact_type) so tampering with envelope metadata
        is detected on decrypt.
        """
        try:
            key = resolve_key(self._secrets, key_id)
            nonce = os.urandom(12)  # fresh, CSPRNG nonce for EVERY operation
            aad = build_aad(ENVELOPE_VERSION, ALGORITHM, artifact_type)
            try:
                ciphertext = AESGCM(key).encrypt(nonce, plaintext, aad)
            except Exception as exc:  # noqa: BLE001 - never leak crypto internals
                raise EncryptionOperationError("encryption operation failed") from exc
        except Exception as exc:
            self._audit_encryption(
                ENCRYPTION_ENCRYPT_FAILED, key_id, artifact_type, success=False, error=exc
            )
            raise

        self._audit_encryption(ENCRYPTION_ENCRYPT_SUCCEEDED, key_id, artifact_type, success=True)
        return EncryptedEnvelope(
            version=ENVELOPE_VERSION,
            algorithm=ALGORITHM,
            key_id=key_id,
            artifact_type=artifact_type,
            nonce=base64.b64encode(nonce).decode("ascii"),
            ciphertext=base64.b64encode(ciphertext).decode("ascii"),
        )

    def decrypt_bytes(self, envelope: EncryptedEnvelope) -> bytes:
        """Decrypt ``envelope``, returning plaintext ONLY if authentication
        succeeds. Wrong key, tampered ciphertext/nonce/AAD all raise the same
        generic ``DecryptionFailedError`` — never partial plaintext."""
        try:
            key = resolve_key(self._secrets, envelope.key_id)
            try:
                plaintext = AESGCM(key).decrypt(
                    envelope.nonce_bytes, envelope.ciphertext_bytes, envelope.aad_bytes()
                )
            except InvalidTag as exc:
                raise DecryptionFailedError("authentication failed") from exc
            except Exception as exc:  # noqa: BLE001 - never leak crypto internals
                raise DecryptionFailedError("decryption failed") from exc
        except Exception as exc:
            self._audit_encryption(
                ENCRYPTION_DECRYPT_FAILED,
                envelope.key_id,
                envelope.artifact_type,
                success=False,
                error=exc,
            )
            raise

        self._audit_encryption(
            ENCRYPTION_DECRYPT_SUCCEEDED, envelope.key_id, envelope.artifact_type, success=True
        )
        return plaintext

    @staticmethod
    def _audit_encryption(
        action: str,
        key_id: str,
        artifact_type: str,
        *,
        success: bool,
        error: Exception | None = None,
    ) -> None:
        metadata = {"algorithm": ALGORITHM, "artifact_type": artifact_type}
        if error is not None:
            # Safe error CATEGORY only (class name) -- never str(exc) / repr()
            # / a stack trace (PART: "No raw exception dumps in audit events").
            metadata["error_category"] = type(error).__name__
        get_audit_service().emit(
            event_type=EventType.ENCRYPTION,
            action=action,
            outcome=Outcome.SUCCESS if success else Outcome.FAILURE,
            severity=Severity.INFO if success else Severity.ERROR,
            resource=Resource(resource_type=ENCRYPTED_ARTIFACT, resource_id=key_id),
            metadata=metadata,
        )

    # --- JSON convenience (explicit UTF-8 JSON; never pickle/eval) --------- #
    def encrypt_json(
        self, obj: object, *, key_id: str, artifact_type: str
    ) -> EncryptedEnvelope:
        payload = json.dumps(obj, separators=(",", ":")).encode("utf-8")
        return self.encrypt_bytes(payload, key_id=key_id, artifact_type=artifact_type)

    def decrypt_json(self, envelope: EncryptedEnvelope) -> object:
        raw = self.decrypt_bytes(envelope)
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise DecryptionFailedError("decrypted content was not valid JSON") from exc


def get_default_encryption_service() -> EncryptionService:
    """Process-wide service wired to the environment-backed secret provider.

    Swapping in a Phase 8 ``VaultSecretProvider`` only requires changing what
    ``get_secret_provider()`` returns — this function and ``EncryptionService``
    need no changes.
    """
    return EncryptionService(get_secret_provider())
