"""API ingestion service: resolves a source and runs the pipeline.

Returns a PII-safe aggregate summary — never entities, payloads, secrets, or
headers. Designed so Phase 9 audit logging can wrap ``run`` to record
API_INGESTION_STARTED / SUCCEEDED / FAILED with safe metadata (source_id,
principal_id, status, aggregate counts, duration) — NOT payloads or tokens.
"""

from __future__ import annotations

import time
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.audit.events.actions import (
    INGESTION_API_COMPLETED,
    INGESTION_API_FAILED,
    INGESTION_API_STARTED,
)
from app.audit.events.enums import EventType, Outcome, Severity
from app.audit.events.models import Resource
from app.audit.events.resources import INGESTION_SOURCE
from app.audit.service import get_audit_service
from app.core.config import settings
from app.ingestion.api.client import ApiConnector
from app.ingestion.api.errors import ApiIngestionError
from app.ingestion.api.registry import ApiSourceRegistry, build_registry_from_config
from app.ingestion.pipelines.api_ingestion_pipeline import run_api_ingestion
from app.schemas.common import utcnow
from app.secrets.provider import get_secret_provider


class ApiIngestionSummary(BaseModel):
    """Safe aggregate outcome of an API ingestion run."""

    model_config = ConfigDict(extra="forbid")

    source_id: str
    started_at: datetime
    completed_at: datetime
    total_records_received: int
    valid_records: int
    invalid_records: int
    duplicate_identifiers: int
    validation_issue_counts: dict[str, int] = Field(default_factory=dict)
    status: str = "succeeded"


class ApiIngestionService:
    def __init__(self, registry: ApiSourceRegistry, connector: ApiConnector) -> None:
        self._registry = registry
        self._connector = connector

    async def run(self, source_id: str) -> ApiIngestionSummary:
        audit = get_audit_service()
        monotonic_start = time.monotonic()
        audit.emit(
            event_type=EventType.INGESTION,
            action=INGESTION_API_STARTED,
            outcome=Outcome.SUCCESS,
            resource=Resource(resource_type=INGESTION_SOURCE, resource_id=source_id),
            metadata={"source_type": "api"},
        )
        try:
            source = self._registry.resolve(source_id)  # UNKNOWN_SOURCE / SOURCE_DISABLED
            started = utcnow()
            result = await run_api_ingestion(source, self._connector)  # ApiIngestionError
        except ApiIngestionError as exc:
            audit.emit(
                event_type=EventType.INGESTION,
                action=INGESTION_API_FAILED,
                outcome=Outcome.FAILURE,
                severity=Severity.WARNING,
                resource=Resource(resource_type=INGESTION_SOURCE, resource_id=source_id),
                duration_ms=(time.monotonic() - monotonic_start) * 1000,
                metadata={"source_type": "api", "error_category": exc.code.value},
            )
            raise
        completed = utcnow()
        r = result.report
        audit.emit(
            event_type=EventType.INGESTION,
            action=INGESTION_API_COMPLETED,
            outcome=Outcome.SUCCESS,
            resource=Resource(resource_type=INGESTION_SOURCE, resource_id=source_id),
            duration_ms=(time.monotonic() - monotonic_start) * 1000,
            metadata={
                "source_type": "api",
                "total_records_received": r.total_rows,
                "valid_records": r.valid_rows,
                "invalid_records": r.invalid_rows,
                "duplicate_identifiers": r.duplicate_client_ids,
                "validation_issue_count": sum(r.validation_issue_counts.values()),
            },
        )
        return ApiIngestionSummary(
            source_id=source_id,
            started_at=started,
            completed_at=completed,
            total_records_received=r.total_rows,
            valid_records=r.valid_rows,
            invalid_records=r.invalid_rows,
            duplicate_identifiers=r.duplicate_client_ids,
            validation_issue_counts=r.validation_issue_counts,
            status="succeeded",
        )


def get_api_ingestion_service() -> ApiIngestionService:
    """Default service wired from configuration (env secrets, real transport).

    FastAPI dependency; tests override it to inject a mock-transport connector and
    a synthetic registry so no real network or secrets are needed.
    """
    registry = build_registry_from_config(settings.api_sources_json)
    connector = ApiConnector(get_secret_provider())
    return ApiIngestionService(registry, connector)
