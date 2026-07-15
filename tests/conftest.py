"""
Shared pytest fixtures.

The test suite keeps all tests deterministic:

- Backend tests use isolated in-memory audit services and synthetic identities.
- Entity intelligence tests use synthetic sanctions data and disable live LLM calls.
- No network, database, external APIs, datasets, or real credentials are required.
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from projecttechm.services import reset_registry


# ---------------------------------------------------------------------------
# Entity Intelligence Test Isolation
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session", autouse=True)
def _pin_ambient_state() -> None:
    """
    Pin environment-dependent behaviour.

    - Use synthetic sanctions fixtures for deterministic tests.
    - Disable live LLM calls during pytest execution.
    """

    os.environ["PROJECTTECHM_SANCTIONS_MODE"] = "sample"
    os.environ.setdefault("PROJECTTECHM_LLM_PROVIDER", "none")

    reset_registry()


# ---------------------------------------------------------------------------
# Backend Application Fixtures
# ---------------------------------------------------------------------------

from app.main import app


TEST_JWT_SECRET = "unit-test-only-jwt-secret-key-0123456789abcdef"


@pytest.fixture(autouse=True)
def _isolate_audit_sink():
    """
    Replace persistent audit storage with an in-memory sink.

    Tests never write into real runtime directories.
    """

    from app.audit.service import (
        AuditService,
        reset_audit_service,
        set_audit_service,
    )
    from app.audit.storage.memory import InMemoryAuditSink

    sink = InMemoryAuditSink()

    set_audit_service(AuditService(sink))

    yield sink

    reset_audit_service()


@pytest.fixture
def client() -> TestClient:
    """
    FastAPI TestClient bound to the application.
    """

    return TestClient(app)


@pytest.fixture
def jwt_secret(monkeypatch) -> str:
    """
    Inject test-only JWT configuration.
    """

    from app.core.config import settings

    monkeypatch.setattr(settings, "jwt_secret_key", TEST_JWT_SECRET)
    monkeypatch.setattr(settings, "jwt_algorithm", "HS256")
    monkeypatch.setattr(
        settings,
        "access_token_expire_minutes",
        15,
    )

    return TEST_JWT_SECRET


@pytest.fixture(scope="session")
def test_identities():
    """
    Synthetic identity records covering roles and inactive users.
    """

    from app.identity.authentication.models import PrincipalType
    from app.identity.authentication.password import hash_password
    from app.identity.authentication.provider import PrincipalRecord
    from app.identity.rbac.roles import Role

    return [
        PrincipalRecord(
            username="analyst",
            principal_id="U-ANALYST",
            password_hash=hash_password("pw-analyst"),
            roles=[Role.COMPLIANCE_ANALYST],
        ),
        PrincipalRecord(
            username="engineer",
            principal_id="U-ENGINEER",
            password_hash=hash_password("pw-engineer"),
            roles=[Role.DATA_ENGINEER],
        ),
        PrincipalRecord(
            username="auditor",
            principal_id="U-AUDITOR",
            password_hash=hash_password("pw-auditor"),
            roles=[Role.AUDITOR],
        ),
        PrincipalRecord(
            username="svc",
            principal_id="S-INGEST",
            password_hash=hash_password("pw-svc"),
            principal_type=PrincipalType.SERVICE,
            roles=[
                Role.SERVICE_ACCOUNT,
                Role.DATA_ENGINEER,
            ],
        ),
        PrincipalRecord(
            username="ghost",
            principal_id="U-GHOST",
            password_hash=hash_password("pw-ghost"),
            roles=[Role.COMPLIANCE_ANALYST],
            is_active=False,
        ),
    ]


@pytest.fixture
def auth_client(jwt_secret, test_identities):
    """
    TestClient with synthetic identity provider override.
    """

    from app.identity.authentication.dependencies import (
        get_identity_provider,
    )
    from app.identity.authentication.provider import (
        DevelopmentIdentityProvider,
    )

    provider = DevelopmentIdentityProvider(test_identities)

    app.dependency_overrides[get_identity_provider] = (
        lambda: provider
    )

    client = TestClient(app)

    def token_for(username: str, password: str) -> str | None:
        response = client.post(
            "/api/v1/auth/token",
            data={
                "username": username,
                "password": password,
            },
        )

        if response.status_code == 200:
            return response.json().get("access_token")

        return None

    client.token_for = token_for  # type: ignore[attr-defined]

    try:
        yield client
    finally:
        app.dependency_overrides.clear()