"""Phase 5 tests: trusted-source registry + SSRF/URL destination validation."""

from __future__ import annotations

import pytest

from app.ingestion.api.errors import ApiErrorCode, ApiIngestionError
from app.ingestion.api.registry import ApiSourceRegistry
from app.ingestion.api.security import validate_destination
from tests._api_helpers import make_source

PUBLIC_RESOLVER = lambda h: ["93.184.216.34"]  # noqa: E731


# --- registry (1-6) ------------------------------------------------------ #
def test_known_enabled_source_resolves() -> None:  # 1
    reg = ApiSourceRegistry([make_source(source_id="s1")])
    assert reg.resolve("s1").source_id == "s1"


def test_unknown_source_rejected() -> None:  # 2
    with pytest.raises(ApiIngestionError) as e:
        ApiSourceRegistry([]).resolve("nope")
    assert e.value.code is ApiErrorCode.UNKNOWN_SOURCE


def test_disabled_source_rejected() -> None:  # 3
    reg = ApiSourceRegistry([make_source(source_id="s1", enabled=False)])
    with pytest.raises(ApiIngestionError) as e:
        reg.resolve("s1")
    assert e.value.code is ApiErrorCode.SOURCE_DISABLED


def test_caller_cannot_override_config() -> None:  # 4, 5, 6
    # The resolved source is server-controlled and frozen; a caller only passes
    # a source_id. The config object itself is immutable.
    src = make_source(source_id="s1")
    with pytest.raises(Exception):
        src.base_url = "https://evil.example.com"  # frozen model
    with pytest.raises(Exception):
        src.field_mapping = {"x": "client_id"}
    with pytest.raises(Exception):
        src.auth_secret_name = "OTHER"


# --- SSRF / URL security (7-18) ----------------------------------------- #
def _rejects(url, allow_insecure=False):
    try:
        validate_destination(url, allow_insecure=allow_insecure, resolve=PUBLIC_RESOLVER)
        return False
    except ApiIngestionError as e:
        return e.code is ApiErrorCode.UNSAFE_DESTINATION


def test_valid_public_https_accepted() -> None:  # 7
    validate_destination("https://kyc.example.com/data", resolve=PUBLIC_RESOLVER)


def test_http_external_rejected() -> None:  # 8
    assert _rejects("http://api.example.com/data")


@pytest.mark.parametrize("url", [
    "https://localhost/data",            # 9
    "https://127.0.0.1/data",            # 10
    "https://[::1]/data",                # 11
    "https://10.0.0.1/data",             # 12 private IPv4
    "https://192.168.1.10/data",         # 12 private IPv4
    "https://[fd00::1]/data",            # 13 private IPv6 (ULA)
    "https://169.254.169.254/latest",    # 14/15 link-local + metadata
    "https://[fe80::1]/data",            # 14 link-local IPv6
    "https://224.0.0.1/data",            # multicast
    "https://0.0.0.0/data",              # unspecified
])
def test_dangerous_destinations_rejected(url) -> None:
    assert _rejects(url)


def test_userinfo_rejected() -> None:  # 16
    assert _rejects("https://user:password@example.com/data")


def test_malformed_url_rejected() -> None:  # 17
    assert _rejects("notaurl")
    assert _rejects("https://")


def test_fragment_rejected() -> None:  # 18
    assert _rejects("https://example.com/data#frag")


def test_test_transport_does_not_weaken_production(monkeypatch) -> None:  # 19
    # allow_insecure permits http+local for a TEST source only...
    validate_destination("http://testserver/kyc", allow_insecure=True)
    validate_destination("https://localhost/kyc", allow_insecure=True)
    # ...but a normal (non-test) source is still fully validated.
    assert _rejects("http://testserver/kyc", allow_insecure=False)
    assert _rejects("https://localhost/kyc", allow_insecure=False)
