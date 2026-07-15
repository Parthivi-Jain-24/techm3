"""File-level validation for KYC inputs (untrusted file threat model).

Checks that make a whole file unusable are enforced here and raised as typed
errors BEFORE any content is parsed: approved-path containment, supported
extension, existence, non-empty, and size limit.

NOTE (production): enterprise malware/AV scanning and content-disarm would run
at this boundary before parsing. It is intentionally out of scope for this
hackathon phase — documented in docs/kyc-ingestion.md.
"""

from __future__ import annotations

from pathlib import Path

from app.core.config import settings
from app.ingestion.connectors.kyc_file_connector import (
    SUPPORTED_EXTENSIONS,
    resolve_kyc_path,
)
from app.ingestion.errors import (
    EmptyFileError,
    FileTooLargeError,
    MissingFileError,
    UnsupportedFileTypeError,
)


def validate_kyc_file(
    filename: str,
    approved_dir: Path | str | None = None,
    max_size_mb: float | None = None,
) -> Path:
    """Validate a KYC input file and return its safe absolute path.

    Order: path containment -> extension -> existence -> size (non-empty and
    under limit). ``approved_dir`` and ``max_size_mb`` are injectable for tests;
    they default to the configured values.
    """
    limit_mb = settings.max_kyc_file_size_mb if max_size_mb is None else max_size_mb

    # 1) Path containment (raises KycPathError on traversal / escape).
    path = resolve_kyc_path(filename, approved_dir=approved_dir)

    # 2) Supported extension (guards misleading extensions from being parsed).
    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise UnsupportedFileTypeError(
            f"unsupported extension {path.suffix!r}; "
            f"allowed: {sorted(SUPPORTED_EXTENSIONS)}"
        )

    # 3) Existence / regular file.
    if not path.is_file():
        raise MissingFileError(f"not a file: {path.name}")

    # 4) Size limits.
    size = path.stat().st_size
    if size == 0:
        raise EmptyFileError(f"empty file: {path.name}")
    max_bytes = limit_mb * 1024 * 1024
    if size > max_bytes:
        raise FileTooLargeError(
            f"file {path.name} is {size} bytes; exceeds limit {max_bytes} bytes "
            f"({limit_mb} MB)"
        )

    return path
