"""Shared pytest fixtures.

All fixtures are fully self-contained: no network, database, external APIs,
datasets, or real credentials are required. Auth fixtures use a clearly
test-only JWT secret and synthetic identities.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app

# Clearly test-only secret (>=32 bytes to satisfy HS256 recommendations).
TEST_JWT_SECRET = "unit-test-only-jwt-secret-key-0123456789abcdef"


@pytest.fixture(autouse=True)
def _isolate_audit_sink():
    """Every test gets an in-memory audit sink instead of the real
    backend/var/audit/audit.jsonl file (Phase 9) -- mirrors the project's
    existing pattern of never letting tests write into real runtime/dataset
    directories (see e.g. encrypted-artifact tests using tmp_path). Tests
    that specifically exercise the JSONL sink construct one explicitly
    against a pytest tmp_path."""
    from app.audit.service import AuditService, reset_audit_service, set_audit_service
    from app.audit.storage.memory import InMemoryAuditSink

    sink = InMemoryAuditSink()
    set_audit_service(AuditService(sink))
    yield sink
    reset_audit_service()


@pytest.fixture
def client() -> TestClient:
    """A FastAPI TestClient bound to the application under test."""
    return TestClient(app)


@pytest.fixture
def jwt_secret(monkeypatch) -> str:
    """Inject a test JWT secret + short expiry into settings for the test."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "jwt_secret_key", TEST_JWT_SECRET)
    monkeypatch.setattr(settings, "jwt_algorithm", "HS256")
    monkeypatch.setattr(settings, "access_token_expire_minutes", 15)
    return TEST_JWT_SECRET


@pytest.fixture(scope="session")
def test_identities():
    """Synthetic identity records covering multiple roles + an inactive user.

    Session-scoped so Argon2 hashing (deliberately slow) runs once for the suite.
    """
    from app.identity.authentication.models import PrincipalType
    from app.identity.authentication.password import hash_password
    from app.identity.authentication.provider import PrincipalRecord
    from app.identity.rbac.roles import Role

    return [
        PrincipalRecord(username="analyst", principal_id="U-ANALYST",
                        password_hash=hash_password("pw-analyst"),
                        roles=[Role.COMPLIANCE_ANALYST]),
        PrincipalRecord(username="engineer", principal_id="U-ENGINEER",
                        password_hash=hash_password("pw-engineer"),
                        roles=[Role.DATA_ENGINEER]),
        PrincipalRecord(username="auditor", principal_id="U-AUDITOR",
                        password_hash=hash_password("pw-auditor"),
                        roles=[Role.AUDITOR]),
        PrincipalRecord(username="svc", principal_id="S-INGEST",
                        password_hash=hash_password("pw-svc"),
                        principal_type=PrincipalType.SERVICE,
                        roles=[Role.SERVICE_ACCOUNT, Role.DATA_ENGINEER]),
        PrincipalRecord(username="ghost", principal_id="U-GHOST",
                        password_hash=hash_password("pw-ghost"),
                        roles=[Role.COMPLIANCE_ANALYST], is_active=False),
    ]


@pytest.fixture
def auth_client(jwt_secret, test_identities):
    """TestClient with the identity provider overridden by synthetic identities,
    plus a helper to obtain bearer tokens."""
    from app.identity.authentication.dependencies import get_identity_provider
    from app.identity.authentication.provider import DevelopmentIdentityProvider

    provider = DevelopmentIdentityProvider(test_identities)
    app.dependency_overrides[get_identity_provider] = lambda: provider
    client = TestClient(app)

    def token_for(username: str, password: str) -> str | None:
        resp = client.post("/api/v1/auth/token",
                           data={"username": username, "password": password})
        return resp.json().get("access_token") if resp.status_code == 200 else None

    client.token_for = token_for  # type: ignore[attr-defined]
    try:
        yield client
    finally:
        app.dependency_overrides.clear()
