"""Payload extraction + explicit source-to-canonical field mapping.

No arbitrary JSONPath / expression engine: only two small, typed payload shapes
(ROOT_LIST, DATA_FIELD) chosen by trusted source config. Untrusted payloads that
don't match are rejected safely.
"""

from __future__ import annotations

from app.ingestion.api.errors import ApiErrorCode, ApiIngestionError
from app.ingestion.api.models import PayloadLocation, TrustedApiSourceConfig


def extract_records(payload: object, source: TrustedApiSourceConfig) -> list[dict]:
    """Return the list of raw record dicts from a parsed JSON payload."""
    if source.payload_location is PayloadLocation.ROOT_LIST:
        container = payload
    else:  # DATA_FIELD
        if not isinstance(payload, dict) or source.data_field not in payload:
            raise ApiIngestionError(
                ApiErrorCode.INVALID_PAYLOAD_SHAPE,
                f"payload missing expected data field '{source.data_field}'",
            )
        container = payload[source.data_field]

    if not isinstance(container, list):
        raise ApiIngestionError(
            ApiErrorCode.INVALID_PAYLOAD_SHAPE, "expected a JSON array of records"
        )
    for item in container:
        if not isinstance(item, dict):
            raise ApiIngestionError(
                ApiErrorCode.INVALID_PAYLOAD_SHAPE, "each record must be a JSON object"
            )
    return container


def map_records(
    records: list[dict], field_mapping: dict[str, str]
) -> tuple[list[str], list[dict[str, str]]]:
    """Apply the explicit source→canonical mapping.

    Produces ``(header, rows)`` keyed by canonical column names, with all values
    coerced to strings so the SHARED normalizer (Phase 2) can validate them
    identically to CSV/XLSX input. JSON booleans/numbers become their string
    forms (e.g. True -> "True", 123 -> "123"); missing source fields -> "".
    """
    header = list(dict.fromkeys(field_mapping.values()))  # canonical targets, ordered/unique
    rows: list[dict[str, str]] = []
    for record in records:
        row: dict[str, str] = {}
        for source_field, canonical in field_mapping.items():
            value = record.get(source_field, "")
            row[canonical] = "" if value is None else str(value)
        rows.append(row)
    return header, rows
