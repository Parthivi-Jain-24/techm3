"""Phase 9 tests: domain audit-event integration (auth, RBAC, ingestion,
encryption, secret access) -- functional correctness of WHAT gets emitted.

See test_audit_leakage.py for the adversarial "never contains X" tests using
synthetic markers.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.audit.events.enums import EventType, Outcome
from app.identity.authentication.dependencies import get_identity_provider
from app.identity.authentication.provider import DevelopmentIdentityProvider
from app.ingestion.api.registry import ApiSourceRegistry
from app.ingestion.services.api_ingestion_service import (
    ApiIngestionService,
    get_api_ingestion_service,
)
from app.main import app
from tests._api_helpers import json_transport, make_connector, make_source
from tests._encryption_helpers import make_service

AUTH = lambda t: {"Authorization": f"Bearer {t}"}  # noqa: E731


def _actions(sink, action: str):
    return [e for e in sink.events if e.action == action]


# --- authentication (29-34) ------------------------------------------------- #
def test_authentication_success_emits_safe_event(auth_client, _isolate_audit_sink) -> None:  # 29
    r = auth_client.post("/api/v1/auth/token", data={"username": "analyst", "password": "pw-analyst"})
    assert r.status_code == 200
    events = _actions(_isolate_audit_sink, "authentication.succeeded")
    assert len(events) == 1
    event = events[0]
    assert event.event_type == EventType.AUTHENTICATION
    assert event.outcome == Outcome.SUCCESS
    assert event.actor.actor_id == "U-ANALYST"
    assert event.metadata["mechanism"] == "password"


def test_authentication_failure_emits_safe_event_without_identity(
    auth_client, _isolate_audit_sink
) -> None:  # 30, 34
    r = auth_client.post(
        "/api/v1/auth/token", data={"username": "analyst", "password": "wrong-password"}
    )
    assert r.status_code == 401
    events = _actions(_isolate_audit_sink, "authentication.failed")
    assert len(events) == 1
    assert events[0].outcome == Outcome.FAILURE
    # No account-enumeration signal: the failed event carries no attempted
    # username/actor identity at all (anonymous actor).
    assert events[0].actor.actor_id == "anonymous"


def test_unknown_username_produces_identical_shaped_failure_event(
    auth_client, _isolate_audit_sink
) -> None:  # 34b
    r = auth_client.post(
        "/api/v1/auth/token", data={"username": "totally-unknown-user", "password": "x"}
    )
    assert r.status_code == 401
    events = _actions(_isolate_audit_sink, "authentication.failed")
    assert len(events) == 1
    assert events[0].actor.actor_id == "anonymous"  # same shape as a known-user wrong-password


def test_rejected_bearer_token_emits_failure_event(auth_client, _isolate_audit_sink) -> None:  # 30b
    r = auth_client.get("/api/v1/security/me", headers=AUTH("this-is-not-a-valid-jwt"))
    assert r.status_code == 401
    events = _actions(_isolate_audit_sink, "authentication.failed")
    assert len(events) == 1
    assert events[0].metadata["reason"] == "INVALID_TOKEN"


# --- authorization (35-39) --------------------------------------------------- #
def test_denied_authorization_is_audited(auth_client, _isolate_audit_sink) -> None:  # 36
    tok = auth_client.token_for("auditor", "pw-auditor")  # AUDITOR lacks KYC_INGEST
    r = auth_client.post("/api/v1/ingestion/api/kyc_provider/run", headers=AUTH(tok))
    assert r.status_code == 403
    events = _actions(_isolate_audit_sink, "authorization.denied")
    assert len(events) == 1
    event = events[0]
    assert event.outcome == Outcome.DENIED
    assert event.actor.actor_id == "U-AUDITOR"
    assert event.resource.resource_id == "kyc_ingest"


def test_allowed_authorization_is_audited(auth_client, _isolate_audit_sink) -> None:  # 35
    app.dependency_overrides[get_api_ingestion_service] = lambda: ApiIngestionService(
        ApiSourceRegistry([make_source(source_id="kyc_provider")]),
        make_connector(json_transport([])),
    )
    try:
        tok = auth_client.token_for("engineer", "pw-engineer")  # DATA_ENGINEER has KYC_INGEST
        r = auth_client.post("/api/v1/ingestion/api/kyc_provider/run", headers=AUTH(tok))
        assert r.status_code == 200
    finally:
        app.dependency_overrides.pop(get_api_ingestion_service, None)
    events = _actions(_isolate_audit_sink, "authorization.allowed")
    assert len(events) == 1
    assert events[0].outcome == Outcome.SUCCESS
    assert events[0].actor.actor_id == "U-ENGINEER"


def test_same_request_id_correlates_authz_and_completion_events(
    auth_client, _isolate_audit_sink
) -> None:  # 14, 38(shape)
    tok = auth_client.token_for("auditor", "pw-auditor")
    r = auth_client.post("/api/v1/ingestion/api/kyc_provider/run", headers=AUTH(tok))
    assert r.status_code == 403
    denied = _actions(_isolate_audit_sink, "authorization.denied")[0]
    completed = _actions(_isolate_audit_sink, "request.completed")[-1]
    assert denied.request_id == completed.request_id == r.headers["x-request-id"]


# --- file ingestion (40, 42-46) ---------------------------------------------- #
def test_file_ingestion_emits_safe_operation_level_events(tmp_path, _isolate_audit_sink) -> None:  # 40
    from app.ingestion.pipelines.kyc_ingestion_pipeline import ingest_kyc_file

    header = [
        "client_id", "client_name", "client_type", "sector", "sector_risk",
        "country", "pep_flag", "sanctions_flag", "fatf_country_flag",
    ]
    row = {
        "client_id": "1", "client_name": "SYNTHETIC_PII_DO_NOT_LOG_666", "client_type": "Corporate",
        "sector": "Technology", "sector_risk": "High", "country": "in",
        "pep_flag": "0", "sanctions_flag": "1", "fatf_country_flag": "0",
    }
    csv_path = tmp_path / "sample.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=header)
        writer.writeheader()
        writer.writerow(row)

    ingest_kyc_file("sample.csv", approved_dir=tmp_path)

    started = _actions(_isolate_audit_sink, "ingestion.file.started")
    completed = _actions(_isolate_audit_sink, "ingestion.file.completed")
    assert len(started) == 1 and len(completed) == 1
    assert completed[0].resource.resource_id == "sample.csv"  # safe basename only
    assert completed[0].metadata["total_rows"] == 1
    assert completed[0].metadata["valid_rows"] == 1
    dumped = completed[0].model_dump_json() + started[0].model_dump_json()
    assert "SYNTHETIC_PII_DO_NOT_LOG_666" not in dumped


def test_file_ingestion_failure_emits_safe_error_category(tmp_path, _isolate_audit_sink) -> None:
    from app.ingestion.errors import MissingFileError
    from app.ingestion.pipelines.kyc_ingestion_pipeline import ingest_kyc_file

    with pytest.raises(MissingFileError):
        ingest_kyc_file("does-not-exist.csv", approved_dir=tmp_path)

    failed = _actions(_isolate_audit_sink, "ingestion.file.failed")
    assert len(failed) == 1
    assert failed[0].outcome == Outcome.FAILURE
    assert failed[0].metadata["error_category"] == "MissingFileError"


# --- API ingestion (41) ------------------------------------------------------ #
def test_api_ingestion_emits_safe_operation_level_events(_isolate_audit_sink) -> None:  # 41
    registry = ApiSourceRegistry([make_source(source_id="kyc_provider")])
    connector = make_connector(json_transport([
        {"customerId": "1", "fullName": "SYNTHETIC_PII_DO_NOT_LOG_666", "kind": "Individual",
         "iso": "in", "industry": "Tech", "risk": "High", "pep": True, "sanctioned": False, "fatf": 0},
    ]))
    service = ApiIngestionService(registry, connector)

    import asyncio

    asyncio.run(service.run("kyc_provider"))

    started = _actions(_isolate_audit_sink, "ingestion.api.started")
    completed = _actions(_isolate_audit_sink, "ingestion.api.completed")
    assert len(started) == 1 and len(completed) == 1
    assert completed[0].resource.resource_id == "kyc_provider"
    assert completed[0].metadata["valid_records"] == 1
    dumped = completed[0].model_dump_json() + started[0].model_dump_json()
    assert "SYNTHETIC_PII_DO_NOT_LOG_666" not in dumped


# --- encryption (47-52) ------------------------------------------------------ #
def test_encryption_emits_safe_event(_isolate_audit_sink) -> None:  # 47, 49
    svc = make_service()
    svc.encrypt_bytes(b'{"x":1}', key_id="test-encryption-key", artifact_type="unit_test")
    events = _actions(_isolate_audit_sink, "encryption.encrypt.succeeded")
    assert len(events) == 1
    assert events[0].resource.resource_id == "test-encryption-key"
    assert events[0].metadata["algorithm"] == "AES-256-GCM"
    assert events[0].metadata["artifact_type"] == "unit_test"


def test_decryption_emits_safe_event(_isolate_audit_sink) -> None:  # 48
    svc = make_service()
    envelope = svc.encrypt_bytes(b'{"x":1}', key_id="test-encryption-key", artifact_type="unit_test")
    _isolate_audit_sink.clear()
    svc.decrypt_bytes(envelope)
    events = _actions(_isolate_audit_sink, "encryption.decrypt.succeeded")
    assert len(events) == 1
    assert events[0].resource.resource_id == "test-encryption-key"


def test_decryption_failure_emits_safe_event_no_plaintext_or_key(_isolate_audit_sink) -> None:
    from app.encryption.errors import DecryptionFailedError

    svc = make_service()
    envelope = svc.encrypt_bytes(b'{"secret":"value"}', key_id="test-encryption-key", artifact_type="t")
    tampered = envelope.model_copy(update={"ciphertext": envelope.ciphertext[:-4] + "AAAA"})
    with pytest.raises(DecryptionFailedError):
        svc.decrypt_bytes(tampered)
    events = _actions(_isolate_audit_sink, "encryption.decrypt.failed")
    assert len(events) == 1
    assert events[0].outcome == Outcome.FAILURE
    assert events[0].metadata["error_category"] in ("DecryptionFailedError",)


# --- secret access (53-55, 59) ----------------------------------------------- #
def test_secret_access_success_is_audited(_isolate_audit_sink) -> None:  # 53, 55
    svc = make_service()
    svc.encrypt_bytes(b"x", key_id="test-encryption-key", artifact_type="t")
    events = _actions(_isolate_audit_sink, "secret.access.succeeded")
    assert len(events) == 1
    assert events[0].resource.resource_id == "test-encryption-key"
    assert events[0].metadata["provider_type"] == "EnvironmentSecretProvider"


def test_secret_access_failure_is_audited(_isolate_audit_sink) -> None:  # 54
    from app.encryption.errors import EncryptionConfigurationError
    from app.encryption.service import EncryptionService
    from app.secrets.provider import EnvironmentSecretProvider

    svc = EncryptionService(EnvironmentSecretProvider({}))  # no key configured
    with pytest.raises(EncryptionConfigurationError):
        svc.encrypt_bytes(b"x", key_id="missing-key", artifact_type="t")
    events = _actions(_isolate_audit_sink, "secret.access.failed")
    assert len(events) == 1
    assert events[0].outcome == Outcome.FAILURE
    assert events[0].resource.resource_id == "missing-key"


def test_audit_subsystem_has_no_dependency_on_secret_provider() -> None:  # 59, no-recursion
    # Static proof (mirrors test_secrets_factory.py's centralization check):
    # the audit sink/service never IMPORTS app.secrets, so writing an audit
    # event can never itself trigger a secret lookup. Checks actual import
    # statements only (a docstring mentioning app.secrets by name for
    # documentation purposes is fine and expected).
    import ast
    import inspect

    import app.audit.service as service_mod
    import app.audit.storage.jsonl as jsonl_mod
    import app.audit.storage.memory as memory_mod

    for mod in (service_mod, jsonl_mod, memory_mod):
        tree = ast.parse(inspect.getsource(mod))
        imported_modules = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_modules.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_modules.add(node.module)
        assert not any(m.startswith("app.secrets") for m in imported_modules)
