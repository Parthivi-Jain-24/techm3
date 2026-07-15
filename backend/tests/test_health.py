"""Phase 1 foundation tests: application import + liveness endpoint."""

from fastapi.testclient import TestClient


def test_app_imports() -> None:
    # Importing the app object at all exercises route wiring and config load.
    from app.main import app

    assert app.title == "Continuous KYC Autonomous Auditor"


def test_liveness_returns_200_and_alive(client: TestClient) -> None:
    response = client.get("/api/v1/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


def test_liveness_path_uses_configured_prefix() -> None:
    # The endpoint must live under the configured versioned prefix, not be
    # hardcoded, so the prefix stays the single source of truth.
    from app.core.config import settings

    assert settings.api_v1_prefix == "/api/v1"
