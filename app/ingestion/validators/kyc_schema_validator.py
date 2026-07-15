"""Source-schema and row-level validation for KYC ingestion.

Responsibilities:
  * confirm the source file carries the required columns;
  * deterministically normalize a single source row to canonical values;
  * emit PII-safe ``ValidationIssue`` objects for anything that fails.

Duplicate detection is cross-row and therefore handled by the pipeline; this
module reports the normalized ``client_id`` so the pipeline can dedupe.
"""

from __future__ import annotations

from typing import NamedTuple

from app.ingestion.errors import SourceSchemaError
from app.ingestion.mapping import (
    BOOLEAN_FIELDS,
    COLUMN_MAP,
    KNOWN_EXTRA_SOURCE_COLUMNS,
    MAX_FIELD_LENGTHS,
    REQUIRED_CANONICAL_FIELDS,
    REQUIRED_SOURCE_COLUMNS,
    normalize_bool,
    normalize_sector_risk,
    normalize_whitespace,
)
from app.ingestion.reports import IssueCode, ValidationIssue, mask_identifier


class SchemaSummary(NamedTuple):
    additional_source_columns: list[str]
    missing_expected_source_columns: list[str]


class RowOutcome(NamedTuple):
    client_id: str  # normalized; "" if blank/missing
    candidate: dict | None  # canonical field->value if pre-dedupe valid, else None
    issues: list[ValidationIssue]


def check_source_schema(header: list[str]) -> SchemaSummary:
    """Raise if required source columns are missing; summarize the rest."""
    present = set(header)
    missing_required = [c for c in REQUIRED_SOURCE_COLUMNS if c not in present]
    if missing_required:
        raise SourceSchemaError(
            f"missing required source columns: {missing_required}"
        )
    mapped = set(COLUMN_MAP.keys())
    additional = [c for c in header if c not in mapped]
    missing_expected = [c for c in KNOWN_EXTRA_SOURCE_COLUMNS if c not in present]
    return SchemaSummary(additional, missing_expected)


def normalize_row(row_number: int, source_row: dict[str, str]) -> RowOutcome:
    """Normalize one source row into canonical values, collecting issues.

    Returns the normalized client_id (for cross-row dedupe), a candidate dict
    (None if the row has any pre-dedupe issue), and the list of issues.
    """
    issues: list[ValidationIssue] = []
    canonical: dict[str, object] = {}

    # Raw client_id first so issues can carry a masked reference.
    client_id = (source_row.get("client_id", "") or "").strip()
    client_ref = mask_identifier(client_id) if client_id else None

    def add(field: str, code: IssueCode, message: str) -> None:
        issues.append(
            ValidationIssue(
                row_number=row_number,
                field=field,
                issue_code=code,
                message=message,
                client_ref=client_ref,
            )
        )

    # --- Required string fields ---
    for field in REQUIRED_CANONICAL_FIELDS:
        raw = source_row.get(field, "")
        value = client_id if field == "client_id" else normalize_whitespace(raw)
        if field == "country":
            value = value.upper()

        if not value:
            add(field, IssueCode.MISSING_REQUIRED_FIELD, f"{field} is blank/missing")
            continue

        limit = MAX_FIELD_LENGTHS.get(field)
        if limit is not None and len(value) > limit:
            add(
                field,
                IssueCode.VALUE_TOO_LONG,
                f"{field} length {len(value)} exceeds max {limit}",
            )
            continue

        canonical[field] = value

    # --- Boolean flags ---
    for field in BOOLEAN_FIELDS:
        raw = source_row.get(field, "")
        try:
            canonical[field] = normalize_bool(raw)
        except ValueError:
            add(field, IssueCode.INVALID_BOOLEAN, f"{field}: unrecognized boolean value")

    # --- Sector risk (categorical) ---
    raw_risk = source_row.get("sector_risk", "")
    try:
        canonical["sector_risk"] = normalize_sector_risk(raw_risk)
    except ValueError:
        add("sector_risk", IssueCode.INVALID_SECTOR_RISK, "unrecognized sector_risk category")

    candidate = None if issues else canonical
    return RowOutcome(client_id=client_id, candidate=candidate, issues=issues)
