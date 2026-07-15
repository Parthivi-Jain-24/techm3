"""AES-256-GCM encryption at rest for sensitive application-managed artifacts.

Scope (Phase 6): explicit, opt-in encryption of application-generated KYC
artifacts (e.g. processed exports) before they touch disk. This is NOT a claim
that every byte on every disk is encrypted — see docs/encryption-at-rest.md for
the exact boundary. No database exists yet, so there is no database-field
encryption; no TLS/vault/audit-middleware here (later phases).
"""

from app.encryption.errors import (
    DecryptionFailedError,
    EncryptedArtifactPathError,
    EncryptionConfigurationError,
    EncryptionOperationError,
    InvalidEncryptionKeyError,
    MalformedEncryptedEnvelopeError,
    UnsupportedAlgorithmError,
    UnsupportedEnvelopeVersionError,
)
from app.encryption.artifact_store import EncryptedArtifactStore, get_default_artifact_store
from app.encryption.models import ALGORITHM, ENVELOPE_VERSION, EncryptedEnvelope
from app.encryption.service import EncryptionService, get_default_encryption_service

__all__ = [
    "EncryptionService",
    "get_default_encryption_service",
    "EncryptedArtifactStore",
    "get_default_artifact_store",
    "EncryptedEnvelope",
    "ALGORITHM",
    "ENVELOPE_VERSION",
    "EncryptionConfigurationError",
    "InvalidEncryptionKeyError",
    "UnsupportedEnvelopeVersionError",
    "UnsupportedAlgorithmError",
    "MalformedEncryptedEnvelopeError",
    "EncryptionOperationError",
    "DecryptionFailedError",
    "EncryptedArtifactPathError",
]
