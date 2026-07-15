"""API ingestion pipeline (orchestration only).

Fetch (safe outbound HTTP) → extract payload → map source→canonical → reuse the
SHARED Phase 2 normalization (`normalize_batch`) → structured IngestionResult.
No route logic here; callable directly from Python (jobs, service identities).
"""

from __future__ import annotations

from app.ingestion.api.client import ApiConnector
from app.ingestion.api.errors import ApiErrorCode, ApiIngestionError
from app.ingestion.api.extraction import extract_records, map_records
from app.ingestion.api.models import TrustedApiSourceConfig
from app.ingestion.errors import SourceSchemaError
from app.ingestion.pipelines.kyc_ingestion_pipeline import normalize_batch
from app.ingestion.reports import IngestionResult


async def run_api_ingestion(
    source: TrustedApiSourceConfig, connector: ApiConnector
) -> IngestionResult:
    """Run one API ingestion for a resolved trusted source."""
    payload = await connector.fetch(source)               # safe HTTP + JSON parse
    records = extract_records(payload, source)            # shape validation
    header, rows = map_records(records, source.field_mapping)  # explicit mapping
    try:
        # Same validation/normalization/dedup/reporting as CSV & XLSX.
        return normalize_batch(header, rows, source.source_id)
    except SourceSchemaError:
        # Required canonical columns missing from the mapping/payload.
        raise ApiIngestionError(
            ApiErrorCode.SCHEMA_VALIDATION_FAILED,
            "payload did not satisfy the required KYC schema",
        )
