"""Typed errors for KYC ingestion.

File-level problems (which make the *whole* file unusable) are raised as
exceptions. Row-level problems are collected as ``ValidationIssue`` objects and
never raised — see ``app.ingestion.reports``.
"""

from __future__ import annotations


class KycIngestionError(Exception):
    """Base class for all KYC ingestion errors."""


class KycPathError(KycIngestionError):
    """The requested path is outside the approved KYC directory / is unsafe."""


class MissingFileError(KycIngestionError):
    """The requested file does not exist or is not a regular file."""


class UnsupportedFileTypeError(KycIngestionError):
    """The file extension is not an accepted KYC input format."""


class EmptyFileError(KycIngestionError):
    """The file is empty (zero bytes / no data rows)."""


class FileTooLargeError(KycIngestionError):
    """The file exceeds the configured maximum size."""


class SourceSchemaError(KycIngestionError):
    """Required source columns are missing, so no row can be normalized."""


class CorruptFileError(KycIngestionError):
    """The file could not be parsed as its declared format (e.g. a corrupt or
    non-spreadsheet .xlsx). Raised BEFORE any row is processed; the underlying
    parser error is never surfaced to the caller (no library internals leaked)."""
