"""Typed configuration for a trusted API source (server-controlled).

The model is small and declarative — NOT a workflow language. It never contains
secret VALUES: authentication references a secret by logical NAME only.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class HttpMethod(str, Enum):
    GET = "GET"
    POST = "POST"  # only for trusted sources that require it for retrieval


class ApiAuthType(str, Enum):
    NONE = "none"
    BEARER_TOKEN = "bearer_token"
    API_KEY_HEADER = "api_key_header"


class PayloadLocation(str, Enum):
    ROOT_LIST = "root_list"      # payload is a top-level JSON array
    DATA_FIELD = "data_field"    # payload is {"<data_field>": [ ... ]}


class TrustedApiSourceConfig(BaseModel):
    """Immutable, explicit configuration for one trusted external KYC source."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str = Field(..., min_length=1)
    base_url: str = Field(..., min_length=1)
    endpoint_path: str = ""
    http_method: HttpMethod = HttpMethod.GET

    # Authentication: type + a LOGICAL secret name (never the value).
    auth_type: ApiAuthType = ApiAuthType.NONE
    auth_secret_name: str | None = None       # e.g. "KYC_PROVIDER_API_TOKEN"
    auth_header_name: str | None = None        # for API_KEY_HEADER, e.g. "X-API-Key"

    expected_content_type: str = "application/json"
    payload_location: PayloadLocation = PayloadLocation.ROOT_LIST
    data_field: str | None = None              # required when DATA_FIELD

    # Explicit, server-controlled source-field -> canonical-field mapping.
    field_mapping: dict[str, str] = Field(default_factory=dict)

    # Optional per-source overrides (fall back to settings when None).
    max_response_size_mb: float | None = None

    # Redirects OFF by default; TLS verification is NEVER disabled anywhere.
    follow_redirects: bool = False

    # TEST-ONLY: permits http:// + loopback/local hosts via injected transport.
    # Defaults False so production behaviour is always secure. This lives on the
    # server-controlled source config and is NOT settable by API callers.
    allow_insecure: bool = False

    enabled: bool = True

    @property
    def url(self) -> str:
        base = self.base_url.rstrip("/")
        path = self.endpoint_path.lstrip("/")
        return f"{base}/{path}" if path else base

    @model_validator(mode="after")
    def _check_consistency(self) -> "TrustedApiSourceConfig":
        if self.auth_type is ApiAuthType.BEARER_TOKEN and not self.auth_secret_name:
            raise ValueError("BEARER_TOKEN auth requires auth_secret_name")
        if self.auth_type is ApiAuthType.API_KEY_HEADER and not (
            self.auth_secret_name and self.auth_header_name
        ):
            raise ValueError("API_KEY_HEADER auth requires auth_secret_name and auth_header_name")
        if self.payload_location is PayloadLocation.DATA_FIELD and not self.data_field:
            raise ValueError("DATA_FIELD payload_location requires data_field")
        if not self.field_mapping:
            raise ValueError("field_mapping must not be empty")
        return self
