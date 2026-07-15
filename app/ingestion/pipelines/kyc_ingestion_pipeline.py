"""KYC ingestion pipeline: orchestration only.

Flow:
    validate file -> read CSV -> check source schema -> normalize rows
    -> detect duplicate client_ids -> build NormalizedKYCEntity objects
    -> assemble a PII-safe DataQualityReport.

Deliberately in-memory: no database, no API. Optional JSONL output is written
only when explicitly requested (never on import).
"""

from __future__ import annotations

import collections
import json
import time
from pathlib import Path

from app.audit.events.actions import (
    INGESTION_FILE_COMPLETED,
    INGESTION_FILE_FAILED,
    INGESTION_FILE_STARTED,
)
from app.audit.events.enums import EventType, Outcome, Severity
from app.audit.events.models import Resource
from app.audit.events.resources import INGESTION_SOURCE
from app.audit.service import get_audit_service
from app.core.config import settings
from app.encryption.artifact_store import EncryptedArtifactStore, get_default_artifact_store
from app.ingestion.connectors.kyc_file_connector import read_kyc_rows
from app.ingestion.errors import KycIngestionError
from app.ingestion.reports import (
    DataQualityReport,
    IngestionResult,
    IssueCode,
    ValidationIssue,
    mask_identifier,
)
from app.ingestion.validators.file_validator import validate_kyc_file
from app.ingestion.validators.kyc_schema_validator import (
    check_source_schema,
    normalize_row,
)
from app.schemas.kyc import NormalizedKYCEntity


def normalize_batch(
    header: list[str],
    rows: list[dict[str, str]],
    source_file: str,
) -> IngestionResult:
    """Shared normalization for a batch of source records (channel-agnostic).

    Used by BOTH file (CSV/XLSX) and API ingestion so validation, normalization,
    duplicate handling, and reporting are identical regardless of channel.
    ``rows`` must be keyed by canonical source-column names; ``header`` lists the
    columns present. Raises ``SourceSchemaError`` if required columns are absent;
    row-level problems are collected as issues and never raise.
    """
    schema = check_source_schema(header)

    # --- Per-record normalization (pre-dedupe) ---
    outcomes = [normalize_row(i, row) for i, row in enumerate(rows, start=1)]

    # --- Cross-record duplicate detection over non-blank client_ids ---
    id_counts = collections.Counter(o.client_id for o in outcomes if o.client_id)
    duplicate_ids = {cid for cid, n in id_counts.items() if n > 1}

    entities: list[NormalizedKYCEntity] = []
    issues: list[ValidationIssue] = []

    for row_number, outcome in enumerate(outcomes, start=1):
        row_issues = list(outcome.issues)
        candidate = outcome.candidate

        if outcome.client_id and outcome.client_id in duplicate_ids:
            # Do NOT silently pick a winner: every occurrence is flagged and
            # none of the duplicated records are emitted.
            row_issues.append(
                ValidationIssue(
                    row_number=row_number,
                    field="client_id",
                    issue_code=IssueCode.DUPLICATE_CLIENT_ID,
                    message=f"client_id occurs {id_counts[outcome.client_id]} times",
                    client_ref=mask_identifier(outcome.client_id),
                )
            )
            candidate = None

        issues.extend(row_issues)
        if candidate is not None:
            entities.append(NormalizedKYCEntity(**candidate))

    report = _build_report(source_file, len(rows), entities, issues, duplicate_ids, schema)
    return IngestionResult(entities=entities, issues=issues, report=report)


def ingest_kyc_file(
    filename: str,
    approved_dir: Path | str | None = None,
    max_size_mb: float | None = None,
) -> IngestionResult:
    """Validate, read, and normalize one KYC file into canonical entities.

    File-level problems raise typed errors (see app.ingestion.errors). Row-level
    problems are collected as issues and never raise.
    """
    # Safe basename only, even before path validation succeeds -- never the
    # raw caller-supplied string, which could contain traversal segments or
    # an absolute path that would leak local filesystem structure (PART C/I).
    safe_source_id = Path(filename).name
    # Extension is only a hint here (safe: it's the basename); it becomes
    # authoritative after validate_kyc_file confirms it is supported.
    source_format = Path(safe_source_id).suffix.lower().lstrip(".") or "unknown"
    audit = get_audit_service()
    started = time.monotonic()
    audit.emit(
        event_type=EventType.INGESTION,
        action=INGESTION_FILE_STARTED,
        outcome=Outcome.SUCCESS,
        resource=Resource(resource_type=INGESTION_SOURCE, resource_id=safe_source_id),
        metadata={"source_type": "file", "source_format": source_format},
    )
    try:
        path = validate_kyc_file(filename, approved_dir=approved_dir, max_size_mb=max_size_mb)
        header, rows = read_kyc_rows(path)
        result = normalize_batch(header, rows, path.name)
    except KycIngestionError as exc:
        audit.emit(
            event_type=EventType.INGESTION,
            action=INGESTION_FILE_FAILED,
            outcome=Outcome.FAILURE,
            severity=Severity.WARNING,
            resource=Resource(resource_type=INGESTION_SOURCE, resource_id=safe_source_id),
            duration_ms=(time.monotonic() - started) * 1000,
            metadata={
                "source_type": "file",
                "source_format": source_format,
                "error_category": type(exc).__name__,
            },
        )
        raise

    r = result.report
    audit.emit(
        event_type=EventType.INGESTION,
        action=INGESTION_FILE_COMPLETED,
        outcome=Outcome.SUCCESS,
        resource=Resource(resource_type=INGESTION_SOURCE, resource_id=r.source_file),
        duration_ms=(time.monotonic() - started) * 1000,
        metadata={
            "source_type": "file",
            "source_format": source_format,
            "total_rows": r.total_rows,
            "valid_rows": r.valid_rows,
            "invalid_rows": r.invalid_rows,
            "duplicate_client_ids": r.duplicate_client_ids,
            "validation_issue_count": sum(r.validation_issue_counts.values()),
        },
    )
    return result


def _build_report(
    source_file: str,
    total_rows: int,
    entities: list[NormalizedKYCEntity],
    issues: list[ValidationIssue],
    duplicate_ids: set[str],
    schema,
) -> DataQualityReport:
    issue_counts: dict[str, int] = collections.Counter(
        i.issue_code.value for i in issues
    )
    missing_field_counts: dict[str, int] = collections.Counter(
        i.field for i in issues if i.issue_code == IssueCode.MISSING_REQUIRED_FIELD
    )
    valid_rows = len(entities)
    return DataQualityReport(
        source_file=source_file,
        total_rows=total_rows,
        valid_rows=valid_rows,
        invalid_rows=total_rows - valid_rows,
        duplicate_client_ids=len(duplicate_ids),
        missing_required_field_counts=dict(missing_field_counts),
        validation_issue_counts=dict(issue_counts),
        additional_source_columns=list(schema.additional_source_columns),
        missing_expected_source_columns=list(schema.missing_expected_source_columns),
    )


def write_processed_jsonl(result: IngestionResult, out_path: Path) -> Path:
    """Write normalized entities to a JSONL dev artifact (explicit opt-in).

    Never called on import. Output must live under a git-ignored directory
    (data/processed/). Overwrites the target artifact, never source data.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        for entity in result.entities:
            fh.write(json.dumps(entity.model_dump(mode="json")) + "\n")
    return out_path


def default_processed_path(source_file: str) -> Path:
    stem = Path(source_file).stem
    return settings.kyc_processed_path / f"{stem}.normalized.jsonl"


def export_encrypted_kyc_artifact(
    result: IngestionResult,
    filename: str,
    *,
    key_id: str | None = None,
    store: EncryptedArtifactStore | None = None,
) -> Path:
    """Export normalized entities through the AES-256-GCM encrypted artifact
    store (Phase 6) — the PREFERRED path for persisting sensitive normalized
    KYC output, in contrast to :func:`write_processed_jsonl`'s plaintext dev
    artifact. Explicit opt-in; never called on import. No plaintext file is
    written at any point — entities are serialized in memory and encrypted
    directly. Reuses the existing NormalizedKYCEntity; no new normalization.
    """
    store = store or get_default_artifact_store()
    key_id = key_id or settings.encryption_key_id
    payload = [e.model_dump(mode="json") for e in result.entities]
    return store.write_json(
        filename, payload, key_id=key_id, artifact_type="normalized_kyc_entities"
    )
