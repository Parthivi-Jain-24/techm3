"""Structured, PII-safe result models for KYC ingestion.

None of these models carry full raw rows or raw customer names. Where an
identifier is useful for diagnostics it is masked (see ``mask_identifier``).
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import utcnow
from app.schemas.kyc import NormalizedKYCEntity


def mask_identifier(value: str) -> str:
    """Return a PII-safe, non-reversible-ish reference for an identifier.

    Keeps the last 2 characters for correlation and masks the rest, so raw
    identifiers do not leak into reports or logs. Empty input -> "***".
    """
    v = (value or "").strip()
    if not v:
        return "***"
    if len(v) <= 2:
        return "*" * len(v)
    return "*" * (len(v) - 2) + v[-2:]


class IssueCode(str, Enum):
    """Small, documented set of row-level validation issue codes."""

    MISSING_REQUIRED_FIELD = "missing_required_field"
    INVALID_BOOLEAN = "invalid_boolean"
    INVALID_SECTOR_RISK = "invalid_sector_risk"
    DUPLICATE_CLIENT_ID = "duplicate_client_id"
    VALUE_TOO_LONG = "value_too_long"


class ValidationIssue(BaseModel):
    """A single row-level validation problem.

    Deliberately excludes the full raw row and raw customer names. ``field`` is
    the canonical field name; ``message`` is a short, PII-safe description.
    """

    model_config = ConfigDict(extra="forbid")

    row_number: int = Field(
        ..., description="1-based data row number (excludes the header row)."
    )
    field: str = Field(..., description="Canonical field the issue concerns.")
    issue_code: IssueCode = Field(..., description="Machine-readable issue code.")
    message: str = Field(..., description="Short PII-safe description.")
    client_ref: str | None = Field(
        default=None,
        description="Masked client_id for correlation, when safe/available.",
    )


class DataQualityReport(BaseModel):
    """Aggregate, PII-safe data-quality summary for one ingested file."""

    model_config = ConfigDict(extra="forbid")

    source_file: str = Field(..., description="Source file NAME only (no path).")
    total_rows: int = Field(..., description="Total data rows read (excl. header).")
    valid_rows: int = Field(..., description="Rows that produced a NormalizedKYCEntity.")
    invalid_rows: int = Field(..., description="Rows with >=1 validation issue.")
    duplicate_client_ids: int = Field(
        ..., description="Count of client_id VALUES that occur more than once."
    )
    missing_required_field_counts: dict[str, int] = Field(
        default_factory=dict, description="Per-field count of missing_required_field."
    )
    validation_issue_counts: dict[str, int] = Field(
        default_factory=dict, description="Per issue_code totals."
    )
    additional_source_columns: list[str] = Field(
        default_factory=list,
        description="Source columns present but not mapped to the contract.",
    )
    missing_expected_source_columns: list[str] = Field(
        default_factory=list,
        description="Expected optional source columns that were absent.",
    )
    generated_at: datetime = Field(default_factory=utcnow)


class IngestionResult(BaseModel):
    """Full in-memory outcome of an ingestion run.

    ``entities`` are the successfully normalized canonical records; ``issues``
    is the PII-safe issue list; ``report`` is the aggregate summary.
    """

    model_config = ConfigDict(extra="forbid")

    entities: list[NormalizedKYCEntity] = Field(default_factory=list)
    issues: list[ValidationIssue] = Field(default_factory=list)
    report: DataQualityReport
