"""Encrypted artifact storage boundary.

Only ``EncryptedEnvelope`` JSON ever touches disk here — never plaintext, never
a plaintext temp file. Path resolution mirrors the Phase 2
``resolve_kyc_path`` pattern: writes/reads are restricted to the approved
``data/encrypted/`` directory, rejecting absolute paths, ``..`` traversal, and
symlink escapes. Writes are atomic (temp file in the same directory, fsync,
then atomic replace) so a crash never leaves a partially-written artifact, and
the original raw/source datasets are never touched.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from app.core.config import settings
from app.encryption.errors import EncryptedArtifactPathError
from app.encryption.models import EncryptedEnvelope
from app.encryption.service import EncryptionService

ARTIFACT_EXTENSION = ".enc.json"


def _approved_root(approved_dir: Path | str | None) -> Path:
    root = Path(approved_dir) if approved_dir is not None else settings.encrypted_artifact_path
    return root.resolve()


def resolve_artifact_path(filename: str, approved_dir: Path | str | None = None) -> Path:
    """Resolve ``filename`` to an absolute path INSIDE the approved encrypted
    directory. Rejects absolute paths, traversal, and symlink escapes."""
    if not filename or not filename.strip():
        raise EncryptedArtifactPathError("empty filename")

    root = _approved_root(approved_dir)
    raw = filename.strip()
    if Path(raw).is_absolute() or raw.startswith(("/", "\\")):
        raise EncryptedArtifactPathError("absolute paths are not allowed")
    if ".." in Path(raw).parts:
        raise EncryptedArtifactPathError("path traversal ('..') is not allowed")

    candidate = (root / raw).resolve()
    if candidate != root and root not in candidate.parents:
        raise EncryptedArtifactPathError(
            "resolved path escapes the approved encrypted-artifact directory"
        )
    return candidate


class EncryptedArtifactStore:
    """Writes/reads AES-256-GCM encrypted artifacts under an approved directory."""

    def __init__(self, service: EncryptionService, approved_dir: Path | str | None = None) -> None:
        self._service = service
        self._approved_dir = approved_dir

    def write_bytes(
        self, filename: str, plaintext: bytes, *, key_id: str, artifact_type: str
    ) -> Path:
        """Encrypt ``plaintext`` and atomically write the envelope to disk.

        Only the encrypted envelope's JSON bytes are written — plaintext never
        touches disk, not even transiently.
        """
        envelope = self._service.encrypt_bytes(plaintext, key_id=key_id, artifact_type=artifact_type)
        return self._write_envelope(filename, envelope)

    def write_json(
        self, filename: str, obj: object, *, key_id: str, artifact_type: str
    ) -> Path:
        envelope = self._service.encrypt_json(obj, key_id=key_id, artifact_type=artifact_type)
        return self._write_envelope(filename, envelope)

    def _write_envelope(self, filename: str, envelope: EncryptedEnvelope) -> Path:
        target = resolve_artifact_path(filename, self._approved_dir)
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = envelope.model_dump_json().encode("utf-8")

        # Atomic write: temp file in the SAME directory (so os.replace is an
        # atomic rename on the same filesystem), fsync, then atomic replace.
        # Never leaves a partially-written final artifact; cleans up on failure.
        fd, tmp_name = tempfile.mkstemp(
            dir=str(target.parent), prefix=f".{target.name}.", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(payload)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp_name, target)
        except BaseException:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise
        return target

    def read_envelope(self, filename: str) -> EncryptedEnvelope:
        path = resolve_artifact_path(filename, self._approved_dir)
        if not path.is_file():
            raise EncryptedArtifactPathError(f"not a file: {path.name}")
        return EncryptedEnvelope.model_validate_json(path.read_text(encoding="utf-8"))

    def read_bytes(self, filename: str) -> bytes:
        return self._service.decrypt_bytes(self.read_envelope(filename))

    def read_json(self, filename: str) -> object:
        return self._service.decrypt_json(self.read_envelope(filename))


def get_default_artifact_store() -> EncryptedArtifactStore:
    """Process-wide store using the default encryption service + approved dir."""
    from app.encryption.service import get_default_encryption_service

    return EncryptedArtifactStore(get_default_encryption_service())
