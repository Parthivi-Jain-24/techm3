"""Phase 8 tests: health/liveness stays independent of Vault availability."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_liveness_independent_of_vault_configuration(monkeypatch) -> None:  # 56
    from app.core.config import settings

    # Configure vault mode pointing at an address nothing listens on — the
    # liveness endpoint must still respond; it never touches SecretProvider.
    monkeypatch.setattr(settings, "secrets_provider", "vault")
    monkeypatch.setattr(settings, "vault_addr", "http://127.0.0.1:1")

    r = client.get("/api/v1/health/live")
    assert r.status_code == 200
    assert r.json() == {"status": "alive"}


def test_no_readiness_endpoint_added_this_phase() -> None:  # 57
    # No new health/readiness surface was introduced for Vault — documented
    # behavior, not a redesign of the existing health architecture.
    r = client.get("/api/v1/health/ready")
    assert r.status_code == 404


def test_health_response_exposes_no_vault_or_secret_data() -> None:  # 58
    r = client.get("/api/v1/health/live")
    body = r.text.lower()
    for banned in ("vault", "token", "secret", "key"):
        assert banned not in body
