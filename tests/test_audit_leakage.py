"""Phase 9 CRITICAL leakage tests.

Uses synthetic, clearly-marked values ONLY (never real secrets/PII). Each
test proves one specific marker never appears anywhere in captured audit
output, across every event emitted during the scenario -- not just the one
event a naive implementation might think to check.
"""

from __future__ import annotations

import asyncio

import pytest

from app.encryption.errors import EncryptionConfigurationError
from app.encryption.service import EncryptionService
from app.ingestion.api.registry import ApiSourceRegistry
from app.ingestion.services.api_ingestion_service import ApiIngestionService
from app.secrets.provider import EnvironmentSecretProvider
from tests._api_helpers import json_transport, make_connector, make_source

SYNTHETIC_PASSWORD = "SYNTHETIC_PASSWORD_DO_NOT_LOG_111"
SYNTHETIC_JWT = "SYNTHETIC_JWT_DO_NOT_LOG_222"
SYNTHETIC_VAULT_TOKEN = "SYNTHETIC_VAULT_TOKEN_DO_NOT_LOG_333"
SYNTHETIC_API_KEY = "SYNTHETIC_API_KEY_DO_NOT_LOG_444"
SYNTHETIC_ENCRYPTION_KEY = "SYNTHETIC_ENCRYPTION_KEY_DO_NOT_LOG_555"
SYNTHETIC_PII = "SYNTHETIC_PII_DO_NOT_LOG_666"
SYNTHETIC_BODY_SECRET = "SYNTHETIC_BODY_SECRET_DO_NOT_LOG_777"
SYNTHETIC_QUERY_TOKEN = "SYNTHETIC_QUERY_TOKEN_DO_NOT_LOG_888"
SYNTHETIC_SECRET_VALUE = "SYNTHETIC_SECRET_VALUE_DO_NOT_LOG_999"


def _dump_all(sink) -> str:
    return "\n".join(e.model_dump_json() for e in sink.events)


# --- password (35) ----------------------------------------------------------- #
def test_password_marker_never_appears_in_audit_output(auth_client, _isolate_audit_sink) -> None:
    auth_client.post(
        "/api/v1/auth/token", data={"username": "analyst", "password": SYNTHETIC_PASSWORD}
    )
    assert SYNTHETIC_PASSWORD not in _dump_all(_isolate_audit_sink)


# --- JWT (36) ------------------------------------------------------------------ #
def test_jwt_marker_never_appears_in_audit_output(auth_client, _isolate_audit_sink) -> None:
    fake_jwt = f"header.{SYNTHETIC_JWT}.signature"
    auth_client.get("/api/v1/security/me", headers={"Authorization": f"Bearer {fake_jwt}"})
    assert SYNTHETIC_JWT not in _dump_all(_isolate_audit_sink)


# --- Vault token (37) ----------------------------------------------------------- #
def test_vault_token_marker_never_appears_in_audit_output(
    monkeypatch, _isolate_audit_sink
) -> None:
    from app.core.config import settings
    from app.secrets.exceptions import SecretBackendUnavailableError
    from app.secrets.factory import reset_provider_cache, resolve_secret_provider

    monkeypatch.setenv("VAULT_TOKEN", SYNTHETIC_VAULT_TOKEN)
    monkeypatch.setattr(settings, "vault_addr", "http://127.0.0.1:1")  # nothing listens
    reset_provider_cache()
    try:
        provider = resolve_secret_provider("vault")
        svc = EncryptionService(provider)
        with pytest.raises(SecretBackendUnavailableError):
            svc.encrypt_bytes(b"x", key_id="kyc-data-key-v1", artifact_type="t")
    finally:
        reset_provider_cache()
    assert SYNTHETIC_VAULT_TOKEN not in _dump_all(_isolate_audit_sink)


# --- API key / credential (38) --------------------------------------------------- #
def test_api_credential_marker_never_appears_in_audit_output(_isolate_audit_sink) -> None:
    registry = ApiSourceRegistry([make_source(source_id="kyc_provider")])
    connector = make_connector(
        json_transport([{"customerId": "1", "fullName": "x", "kind": "Individual", "iso": "in",
                          "industry": "Tech", "risk": "High", "pep": False, "sanctioned": False,
                          "fatf": 0}]),
        secrets={"KYC_TOKEN": SYNTHETIC_API_KEY},
    )
    service = ApiIngestionService(registry, connector)
    asyncio.run(service.run("kyc_provider"))
    assert SYNTHETIC_API_KEY not in _dump_all(_isolate_audit_sink)


# --- encryption key material (39) ------------------------------------------------ #
def test_encryption_key_material_never_appears_in_audit_output(_isolate_audit_sink) -> None:
    import base64

    key_b64 = base64.b64encode(SYNTHETIC_ENCRYPTION_KEY.ljust(32, "0").encode()[:32]).decode()
    provider = EnvironmentSecretProvider({"unit-test-key": key_b64})
    svc = EncryptionService(provider)
    envelope = svc.encrypt_bytes(b'{"data": 1}', key_id="unit-test-key", artifact_type="t")
    svc.decrypt_bytes(envelope)
    dumped = _dump_all(_isolate_audit_sink)
    assert key_b64 not in dumped
    assert SYNTHETIC_ENCRYPTION_KEY not in dumped


# --- PII (40) -------------------------------------------------------------------- #
def test_pii_marker_never_appears_in_audit_output(tmp_path, _isolate_audit_sink) -> None:
    import csv

    from app.ingestion.pipelines.kyc_ingestion_pipeline import ingest_kyc_file

    header = ["client_id", "client_name", "client_type", "sector", "sector_risk",
              "country", "pep_flag", "sanctions_flag", "fatf_country_flag"]
    row = {"client_id": "1", "client_name": SYNTHETIC_PII, "client_type": "Corporate",
           "sector": "Technology", "sector_risk": "High", "country": "in",
           "pep_flag": "0", "sanctions_flag": "1", "fatf_country_flag": "0"}
    path = tmp_path / "synthetic.csv"
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=header)
        writer.writeheader()
        writer.writerow(row)

    ingest_kyc_file("synthetic.csv", approved_dir=tmp_path)
    assert SYNTHETIC_PII not in _dump_all(_isolate_audit_sink)


# --- request body (41 / CRITICAL REQUEST-BODY TEST) ------------------------------ #
def test_request_body_secret_never_appears_in_audit_output(client, _isolate_audit_sink) -> None:
    client.post(
        "/api/v1/ingestion/api/whatever/run",
        json={"note": SYNTHETIC_BODY_SECRET, "field_mapping": {"x": SYNTHETIC_BODY_SECRET}},
    )
    assert SYNTHETIC_BODY_SECRET not in _dump_all(_isolate_audit_sink)


# --- query string (42 / CRITICAL QUERY-STRING TEST) ------------------------------ #
def test_query_string_token_never_appears_in_audit_output(client, _isolate_audit_sink) -> None:
    client.get(f"/api/v1/health/live?token={SYNTHETIC_QUERY_TOKEN}")
    dumped = _dump_all(_isolate_audit_sink)
    assert SYNTHETIC_QUERY_TOKEN not in dumped
    assert "?" not in dumped  # no raw query string fragment at all


# --- secret access (CRITICAL SECRET-AUDIT TEST) ----------------------------------- #
def test_secret_value_never_appears_in_audit_output_on_success_or_failure(
    _isolate_audit_sink,
) -> None:
    provider = EnvironmentSecretProvider({"logical-name": SYNTHETIC_SECRET_VALUE})
    svc = EncryptionService(provider)
    # Success path (value retrieved, decoding then fails -- still proves the
    # raw secret value was never captured even though it WAS returned by the
    # provider and briefly held in memory).
    with pytest.raises(Exception):
        svc.encrypt_bytes(b"x", key_id="logical-name", artifact_type="t")
    assert SYNTHETIC_SECRET_VALUE not in _dump_all(_isolate_audit_sink)

    # Failure path (secret absent entirely).
    empty_provider = EnvironmentSecretProvider({})
    svc2 = EncryptionService(empty_provider)
    with pytest.raises(EncryptionConfigurationError):
        svc2.encrypt_bytes(b"x", key_id="also-missing", artifact_type="t")
    assert SYNTHETIC_SECRET_VALUE not in _dump_all(_isolate_audit_sink)


# --- headers / cookies (never audited at all) ------------------------------------- #
def test_cookies_and_full_headers_never_captured(client, _isolate_audit_sink) -> None:
    client.get(
        "/api/v1/health/live",
        headers={"Cookie": "session=SYNTHETIC_SESSION_DO_NOT_LOG", "X-Custom": "irrelevant"},
    )
    dumped = _dump_all(_isolate_audit_sink)
    assert "SYNTHETIC_SESSION_DO_NOT_LOG" not in dumped
    assert "Cookie" not in dumped and "cookie" not in dumped
    # No event has an arbitrary headers-shaped metadata key at all.
    for event in _isolate_audit_sink.events:
        assert "headers" not in event.metadata
