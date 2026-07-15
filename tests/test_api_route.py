"""Phase 5 tests: authenticated/RBAC-protected API-ingestion trigger endpoint."""

from __future__ import annotations

import inspect

import pytest
from fastapi.testclient import TestClient

from app.identity.authentication.dependencies import get_identity_provider
from app.identity.authentication.provider import DevelopmentIdentityProvider
from app.ingestion.api.registry import ApiSourceRegistry
from app.ingestion.services.api_ingestion_service import (
    ApiIngestionService,
    get_api_ingestion_service,
)
from app.main import app
from tests._api_helpers import json_transport, make_connector, make_source

AUTH = lambda t: {"Authorization": f"Bearer {t}"}  # noqa: E731


@pytest.fixture
def ingestion_client(jwt_secret, test_identities):
    """TestClient with identity provider + API ingestion service overridden."""
    provider = DevelopmentIdentityProvider(test_identities)

    registry = ApiSourceRegistry([
        make_source(source_id="kyc_provider"),
        make_source(source_id="disabled_src", enabled=False),
    ])
    connector = make_connector(json_transport([
        {"customerId": "1", "fullName": "John Smith", "kind": "Individual", "iso": "in",
         "industry": "Tech", "risk": "High", "pep": True, "sanctioned": False, "fatf": 0},
    ]))
    service = ApiIngestionService(registry, connector)

    app.dependency_overrides[get_identity_provider] = lambda: provider
    app.dependency_overrides[get_api_ingestion_service] = lambda: service
    client = TestClient(app)

    def token_for(username, password):
        r = client.post("/api/v1/auth/token", data={"username": username, "password": password})
        return r.json().get("access_token") if r.status_code == 200 else None
    client.token_for = token_for  # type: ignore[attr-defined]
    try:
        yield client
    finally:
        app.dependency_overrides.clear()


def test_unauthenticated_returns_401(ingestion_client) -> None:  # 60
    r = ingestion_client.post("/api/v1/ingestion/api/kyc_provider/run")
    assert r.status_code == 401


def test_authenticated_without_permission_returns_403(ingestion_client) -> None:  # 61
    tok = ingestion_client.token_for("auditor", "pw-auditor")  # no KYC_INGEST
    r = ingestion_client.post("/api/v1/ingestion/api/kyc_provider/run", headers=AUTH(tok))
    assert r.status_code == 403


def test_authorized_ingestion_succeeds(ingestion_client) -> None:  # 62
    tok = ingestion_client.token_for("engineer", "pw-engineer")  # DATA_ENGINEER=KYC_INGEST
    r = ingestion_client.post("/api/v1/ingestion/api/kyc_provider/run", headers=AUTH(tok))
    assert r.status_code == 200
    body = r.json()
    assert body["source_id"] == "kyc_provider"
    assert body["status"] == "succeeded"
    assert body["valid_records"] == 1


def test_route_uses_centralized_permission_dependency() -> None:  # 63
    from app.api.routes import ingestion as route_mod
    src = inspect.getsource(route_mod)
    assert "require_permission(Permission.KYC_INGEST)" in src
    assert "role ==" not in src and ".role" not in src  # no ad-hoc role checks


def test_caller_cannot_submit_url_or_records(ingestion_client) -> None:  # 64, 59
    tok = ingestion_client.token_for("engineer", "pw-engineer")
    # Attempt to smuggle a destination URL + mapping in the body — ignored.
    r = ingestion_client.post(
        "/api/v1/ingestion/api/kyc_provider/run",
        headers=AUTH(tok),
        json={"url": "http://169.254.169.254/latest", "field_mapping": {"x": "client_id"}},
    )
    assert r.status_code == 200
    body = r.json()
    # 59: response is an aggregate summary — no entities / raw customer records.
    assert "entities" not in body and "client_name" not in str(body)
    assert set(body.keys()) == {
        "source_id", "started_at", "completed_at", "total_records_received",
        "valid_records", "invalid_records", "duplicate_identifiers",
        "validation_issue_counts", "status",
    }


def test_unknown_source_returns_404(ingestion_client) -> None:
    tok = ingestion_client.token_for("engineer", "pw-engineer")
    r = ingestion_client.post("/api/v1/ingestion/api/nope/run", headers=AUTH(tok))
    assert r.status_code == 404
    assert r.json()["detail"]["error_code"] == "unknown_source"


def test_disabled_source_returns_409(ingestion_client) -> None:
    tok = ingestion_client.token_for("engineer", "pw-engineer")
    r = ingestion_client.post("/api/v1/ingestion/api/disabled_src/run", headers=AUTH(tok))
    assert r.status_code == 409


def test_health_still_public(ingestion_client) -> None:  # 76
    assert ingestion_client.get("/api/v1/health/live").status_code == 200
