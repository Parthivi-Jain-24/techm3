"""Shared helpers for Phase 5 API-ingestion tests (not a test module)."""

from __future__ import annotations

import httpx

from app.ingestion.api.client import ApiConnector
from app.ingestion.api.models import (
    ApiAuthType,
    PayloadLocation,
    TrustedApiSourceConfig,
)
from app.secrets.provider import EnvironmentSecretProvider

# Explicit synthetic source-to-canonical field mapping (source names differ).
FIELD_MAPPING = {
    "customerId": "client_id",
    "fullName": "client_name",
    "kind": "client_type",
    "iso": "country",
    "industry": "sector",
    "risk": "sector_risk",
    "pep": "pep_flag",
    "sanctioned": "sanctions_flag",
    "fatf": "fatf_country_flag",
}


def sample_record(**overrides) -> dict:
    rec = {
        "customerId": "1", "fullName": "John Smith", "kind": "Individual",
        "iso": "in", "industry": "Tech", "risk": "High",
        "pep": True, "sanctioned": False, "fatf": 0,
    }
    rec.update(overrides)
    return rec


def make_source(**overrides) -> TrustedApiSourceConfig:
    """A test source (allow_insecure=True so mock transport / http works)."""
    params = dict(
        source_id="test_source",
        base_url="https://testserver",
        endpoint_path="/kyc",
        auth_type=ApiAuthType.BEARER_TOKEN,
        auth_secret_name="KYC_TOKEN",
        payload_location=PayloadLocation.ROOT_LIST,
        field_mapping=dict(FIELD_MAPPING),
        allow_insecure=True,
    )
    params.update(overrides)
    return TrustedApiSourceConfig(**params)


def transport_from(handler) -> httpx.MockTransport:
    return httpx.MockTransport(handler)


def json_transport(payload, *, status=200, headers=None) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        h = {"content-type": "application/json"}
        if headers:
            h.update(headers)
        import json as _json
        return httpx.Response(status, content=_json.dumps(payload).encode(), headers=h)
    return httpx.MockTransport(handler)


def make_connector(transport, secrets=None) -> ApiConnector:
    resolved = secrets if secrets is not None else {"KYC_TOKEN": "SECRET-123"}
    provider = EnvironmentSecretProvider(resolved)
    # Resolver is unused for allow_insecure sources but injected to avoid DNS.
    return ApiConnector(provider, transport=transport, resolver=lambda h: ["93.184.216.34"])
