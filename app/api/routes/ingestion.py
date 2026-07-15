"""Authenticated, RBAC-protected manual API-ingestion trigger.

INBOUND endpoint: a caller selects only a preconfigured ``source_id``. It cannot
supply a URL, credentials, mapping, TLS, or timeout settings — those are all
server-controlled. This is NOT a generic proxy. Requires KYC_INGEST.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.identity.authentication.models import Principal
from app.identity.authorization.dependencies import require_permission
from app.identity.authorization.permissions import Permission
from app.ingestion.api.errors import ApiErrorCode, ApiIngestionError
from app.ingestion.services.api_ingestion_service import (
    ApiIngestionService,
    ApiIngestionSummary,
    get_api_ingestion_service,
)

router = APIRouter()

# Map safe error codes -> HTTP status. Bodies never contain upstream content.
_STATUS_FOR: dict[ApiErrorCode, int] = {
    ApiErrorCode.UNKNOWN_SOURCE: status.HTTP_404_NOT_FOUND,
    ApiErrorCode.SOURCE_DISABLED: status.HTTP_409_CONFLICT,
    ApiErrorCode.UNSAFE_DESTINATION: status.HTTP_400_BAD_REQUEST,
    ApiErrorCode.AUTHENTICATION_CONFIGURATION_ERROR: status.HTTP_503_SERVICE_UNAVAILABLE,
    ApiErrorCode.UPSTREAM_TIMEOUT: status.HTTP_504_GATEWAY_TIMEOUT,
    ApiErrorCode.UPSTREAM_UNAVAILABLE: status.HTTP_502_BAD_GATEWAY,
    ApiErrorCode.UPSTREAM_RATE_LIMITED: status.HTTP_502_BAD_GATEWAY,
    ApiErrorCode.UPSTREAM_CLIENT_ERROR: status.HTTP_502_BAD_GATEWAY,
    ApiErrorCode.RESPONSE_TOO_LARGE: status.HTTP_502_BAD_GATEWAY,
    ApiErrorCode.INVALID_CONTENT_TYPE: status.HTTP_502_BAD_GATEWAY,
    ApiErrorCode.MALFORMED_JSON: status.HTTP_502_BAD_GATEWAY,
    ApiErrorCode.INVALID_PAYLOAD_SHAPE: status.HTTP_502_BAD_GATEWAY,
    ApiErrorCode.SCHEMA_VALIDATION_FAILED: 422,  # Unprocessable Content
}


@router.post("/api/{source_id}/run", response_model=ApiIngestionSummary)
async def run_api_ingestion_source(
    source_id: str,
    principal: Principal = Depends(require_permission(Permission.KYC_INGEST)),
    service: ApiIngestionService = Depends(get_api_ingestion_service),
) -> ApiIngestionSummary:
    """Trigger ingestion for a trusted, server-configured API source.

    Returns a safe aggregate summary only — never full KYC records or payloads.
    """
    try:
        return await service.run(source_id)
    except ApiIngestionError as exc:
        raise HTTPException(
            status_code=_STATUS_FOR.get(exc.code, status.HTTP_502_BAD_GATEWAY),
            detail={"error_code": exc.code.value, "message": exc.safe_message},
        )
