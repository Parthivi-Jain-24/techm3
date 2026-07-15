"""Phase 8 regression tests: EnvironmentSecretProvider + Phase 5/6 integration
via it remain unchanged after adding centralized provider selection."""

from __future__ import annotations

import base64
import os

from app.encryption.errors import EncryptionConfigurationError
from app.encryption.keys import resolve_key
from app.encryption.service import EncryptionService
from app.secrets.provider import EnvironmentSecretProvider
from tests._api_helpers import make_source


# --- environment provider regression (6-8) --------------------------------- #
def test_environment_secret_retrieval_still_works() -> None:  # 6
    provider = EnvironmentSecretProvider({"my-secret": "value-123"})
    assert provider.get_secret("my-secret") == "value-123"


def test_missing_environment_secret_fails_safely() -> None:  # 7
    provider = EnvironmentSecretProvider({})
    assert provider.get_secret("nonexistent") is None


def test_secret_values_not_in_errors() -> None:  # 8
    provider = EnvironmentSecretProvider({})
    try:
        resolve_key(provider, "missing-key-id")
    except EncryptionConfigurationError as e:
        assert "value-123" not in str(e)


# --- Phase 5 / Phase 6 still work with environment provider (9, 10) -------- #
def test_phase5_api_credential_retrieval_works_with_environment_provider() -> None:  # 9
    import asyncio

    import httpx

    from app.ingestion.api.client import ApiConnector

    provider = EnvironmentSecretProvider({"KYC_TOKEN": "SECRET-VIA-ENV"})
    seen = {}

    def handler(request):
        seen["auth"] = request.headers.get("Authorization")
        return httpx.Response(200, json=[], headers={"content-type": "application/json"})

    conn = ApiConnector(provider, transport=httpx.MockTransport(handler))
    asyncio.run(conn.fetch(make_source()))
    assert seen["auth"] == "Bearer SECRET-VIA-ENV"


def test_phase6_encryption_key_retrieval_works_with_environment_provider() -> None:  # 10
    key_b64 = base64.b64encode(os.urandom(32)).decode()
    provider = EnvironmentSecretProvider({"kyc-data-key-v1": key_b64})
    svc = EncryptionService(provider)
    envelope = svc.encrypt_bytes(b"hello", key_id="kyc-data-key-v1", artifact_type="t")
    assert svc.decrypt_bytes(envelope) == b"hello"
