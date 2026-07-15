"""Phase 8 tests: Phase 5 API-ingestion credential resolution through
VaultSecretProvider — proves the existing ApiConnector needs no changes.
"""

from __future__ import annotations

import asyncio
import inspect
import logging

import httpx

from app.ingestion.api.client import ApiConnector
from app.secrets.provider import EnvironmentSecretProvider
from tests._api_helpers import make_source
from tests._vault_helpers import make_vault_provider

SYNTHETIC_API_TOKEN = "SYNTHETIC_VAULT_SECRET_DO_NOT_LOG_987654"


def _run(coro):
    return asyncio.run(coro)


def test_existing_connector_works_with_environment_provider() -> None:  # 41
    provider = EnvironmentSecretProvider({"KYC_TOKEN": "SECRET-VIA-ENV"})
    seen = {}

    def handler(request):
        seen["auth"] = request.headers.get("Authorization")
        return httpx.Response(200, json=[], headers={"content-type": "application/json"})

    conn = ApiConnector(provider, transport=httpx.MockTransport(handler))
    _run(conn.fetch(make_source()))
    assert seen["auth"] == "Bearer SECRET-VIA-ENV"


def test_connector_receives_credential_resolved_through_vault() -> None:  # 42
    vault_provider, _ = make_vault_provider(data={"KYC_TOKEN": SYNTHETIC_API_TOKEN})
    seen = {}

    def handler(request):
        seen["auth"] = request.headers.get("Authorization")
        return httpx.Response(200, json=[], headers={"content-type": "application/json"})

    conn = ApiConnector(vault_provider, transport=httpx.MockTransport(handler))
    _run(conn.fetch(make_source()))
    assert seen["auth"] == f"Bearer {SYNTHETIC_API_TOKEN}"


def test_api_connector_does_not_directly_depend_on_vault_client() -> None:  # 43
    import app.ingestion.api.client as client_mod

    src = inspect.getsource(client_mod)
    assert "hvac" not in src
    assert "vault" not in src.lower()


def test_api_callers_cannot_choose_arbitrary_vault_paths() -> None:  # 44
    # ApiConnector only ever calls SecretProvider.get_secret(auth_secret_name),
    # where auth_secret_name comes from SERVER-controlled TrustedApiSourceConfig
    # (Phase 5) — there is no parameter anywhere for a caller to supply a
    # mount point or Vault path.
    sig = inspect.signature(ApiConnector._auth_headers)
    assert list(sig.parameters) == ["self", "source"]


def test_api_credential_not_logged(caplog) -> None:  # 45
    vault_provider, _ = make_vault_provider(data={"KYC_TOKEN": SYNTHETIC_API_TOKEN})

    def handler(request):
        return httpx.Response(200, json=[], headers={"content-type": "application/json"})

    conn = ApiConnector(vault_provider, transport=httpx.MockTransport(handler))
    with caplog.at_level(logging.DEBUG):
        _run(conn.fetch(make_source()))
    blob = " ".join(r.getMessage() for r in caplog.records)
    assert SYNTHETIC_API_TOKEN not in blob


def test_api_credential_not_returned_in_ingestion_result() -> None:  # 46
    from app.ingestion.pipelines.api_ingestion_pipeline import run_api_ingestion

    vault_provider, _ = make_vault_provider(data={"KYC_TOKEN": SYNTHETIC_API_TOKEN})

    def handler(request):
        return httpx.Response(200, json=[], headers={"content-type": "application/json"})

    conn = ApiConnector(vault_provider, transport=httpx.MockTransport(handler))
    result = _run(run_api_ingestion(make_source(), conn))
    assert SYNTHETIC_API_TOKEN not in result.report.model_dump_json()
    assert SYNTHETIC_API_TOKEN not in str(result.entities)
