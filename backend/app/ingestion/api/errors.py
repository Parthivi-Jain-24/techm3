"""Safe error taxonomy for API ingestion.

Messages are safe by construction: they never contain secrets, credentialed
URLs, Authorization headers, upstream bodies, or stack traces. The ``retryable``
flag drives the bounded retry policy.
"""

from __future__ import annotations

from enum import Enum


class ApiErrorCode(str, Enum):
    UNKNOWN_SOURCE = "unknown_source"
    SOURCE_DISABLED = "source_disabled"
    UNSAFE_DESTINATION = "unsafe_destination"
    AUTHENTICATION_CONFIGURATION_ERROR = "authentication_configuration_error"
    UPSTREAM_TIMEOUT = "upstream_timeout"
    UPSTREAM_UNAVAILABLE = "upstream_unavailable"
    UPSTREAM_RATE_LIMITED = "upstream_rate_limited"
    UPSTREAM_CLIENT_ERROR = "upstream_client_error"  # 401/403/404/other 4xx
    RESPONSE_TOO_LARGE = "response_too_large"
    INVALID_CONTENT_TYPE = "invalid_content_type"
    MALFORMED_JSON = "malformed_json"
    INVALID_PAYLOAD_SHAPE = "invalid_payload_shape"
    SCHEMA_VALIDATION_FAILED = "schema_validation_failed"


class ApiIngestionError(Exception):
    """A safe, structured ingestion failure."""

    def __init__(self, code: ApiErrorCode, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        # ``message`` MUST be safe (no secrets/URLs-with-creds/bodies).
        self.safe_message = message
        self.retryable = retryable
