"""Phase 5 tests: safe outbound HTTP behavior, secret safety, bounded retries."""

from __future__ import annotations

import asyncio
import logging

import httpx
import pytest

from app.ingestion.api.errors import ApiErrorCode, ApiIngestionError
from app.ingestion.api.models import ApiAuthType
from tests._api_helpers import json_transport, make_connector, make_source


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def fast_retries(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "api_retry_backoff_seconds", 0.0)
    monkeypatch.setattr(settings, "api_max_retries", 2)
    return settings


# --- happy path + content-type (23, 24) ---------------------------------- #
def test_successful_json_accepted() -> None:  # 23
    conn = make_connector(json_transport([{"a": 1}]))
    assert run(conn.fetch(make_source())) == [{"a": 1}]


def test_unexpected_content_type_rejected() -> None:  # 24
    conn = make_connector(json_transport([], headers={"content-type": "text/html"}))
    with pytest.raises(ApiIngestionError) as e:
        run(conn.fetch(make_source()))
    assert e.value.code is ApiErrorCode.INVALID_CONTENT_TYPE


# --- JSON safety (25, 26) ------------------------------------------------ #
def test_malformed_json_rejected() -> None:  # 25
    t = httpx.MockTransport(lambda r: httpx.Response(
        200, content=b"{not json", headers={"content-type": "application/json"}))
    with pytest.raises(ApiIngestionError) as e:
        run(make_connector(t).fetch(make_source()))
    assert e.value.code is ApiErrorCode.MALFORMED_JSON


def test_empty_body_rejected_safely() -> None:  # 26
    t = httpx.MockTransport(lambda r: httpx.Response(
        200, content=b"", headers={"content-type": "application/json"}))
    with pytest.raises(ApiIngestionError) as e:
        run(make_connector(t).fetch(make_source()))
    assert e.value.code is ApiErrorCode.MALFORMED_JSON


# --- size limits (27, 28) ------------------------------------------------ #
def test_oversized_content_length_rejected() -> None:  # 27
    conn = make_connector(json_transport([{"a": 1}]))
    src = make_source(max_response_size_mb=0.000001)  # ~1 byte, well below body
    with pytest.raises(ApiIngestionError) as e:
        run(conn.fetch(src))
    assert e.value.code is ApiErrorCode.RESPONSE_TOO_LARGE


def test_streamed_oversize_rejected_without_content_length() -> None:  # 28
    # Async streaming body => httpx sets NO Content-Length header, so the
    # actual-bytes-read cap must catch it.
    async def _agen():
        yield b"x" * 500
    def handler(request):
        return httpx.Response(200, headers={"content-type": "application/json"},
                              content=_agen())
    conn = make_connector(httpx.MockTransport(handler))
    src = make_source(max_response_size_mb=0.0001)  # ~104 bytes < 500
    with pytest.raises(ApiIngestionError) as e:
        run(conn.fetch(src))
    assert e.value.code is ApiErrorCode.RESPONSE_TOO_LARGE


# --- upstream status handling (29-33, 35) -------------------------------- #
@pytest.mark.parametrize("status,code", [
    (401, ApiErrorCode.UPSTREAM_CLIENT_ERROR),  # 29
    (403, ApiErrorCode.UPSTREAM_CLIENT_ERROR),  # 30
    (404, ApiErrorCode.UPSTREAM_CLIENT_ERROR),  # 31
    (429, ApiErrorCode.UPSTREAM_RATE_LIMITED),  # 32
    (500, ApiErrorCode.UPSTREAM_UNAVAILABLE),   # 33
    (503, ApiErrorCode.UPSTREAM_UNAVAILABLE),
])
def test_upstream_error_status_mapped_safely(status, code, fast_retries) -> None:
    secret = "SECRET-123"
    body = f'{{"secret":"{secret}","stack":"trace"}}'.encode()
    t = httpx.MockTransport(lambda r: httpx.Response(
        status, content=body, headers={"content-type": "application/json"}))
    with pytest.raises(ApiIngestionError) as e:
        run(make_connector(t).fetch(make_source()))
    assert e.value.code is code
    assert secret not in e.value.safe_message  # 35: no upstream body echoed
    assert "trace" not in e.value.safe_message


def test_timeout_handled_safely(fast_retries) -> None:  # 34
    def handler(request):
        raise httpx.ConnectTimeout("boom")
    with pytest.raises(ApiIngestionError) as e:
        run(make_connector(httpx.MockTransport(handler)).fetch(make_source()))
    assert e.value.code is ApiErrorCode.UPSTREAM_TIMEOUT


# --- secret safety (36-42) ----------------------------------------------- #
def test_bearer_token_from_secret_provider_in_header_not_url() -> None:  # 36, 38
    seen = {}
    def handler(request: httpx.Request):
        seen["auth"] = request.headers.get("Authorization")
        seen["url"] = str(request.url)
        return httpx.Response(200, json=[], headers={"content-type": "application/json"})
    run(make_connector(httpx.MockTransport(handler)).fetch(make_source()))
    assert seen["auth"] == "Bearer SECRET-123"
    assert "SECRET-123" not in seen["url"]


def test_api_key_header_from_secret_provider() -> None:  # 37
    seen = {}
    def handler(request: httpx.Request):
        seen["key"] = request.headers.get("X-API-Key")
        return httpx.Response(200, json=[], headers={"content-type": "application/json"})
    src = make_source(auth_type=ApiAuthType.API_KEY_HEADER,
                      auth_secret_name="KYC_TOKEN", auth_header_name="X-API-Key")
    run(make_connector(httpx.MockTransport(handler)).fetch(src))
    assert seen["key"] == "SECRET-123"


def test_missing_secret_is_config_error() -> None:
    conn = make_connector(json_transport([]), secrets={})  # no secret configured
    with pytest.raises(ApiIngestionError) as e:
        run(conn.fetch(make_source()))
    assert e.value.code is ApiErrorCode.AUTHENTICATION_CONFIGURATION_ERROR


def test_headers_and_secret_not_logged(caplog) -> None:  # 41, 42
    conn = make_connector(json_transport([]))
    with caplog.at_level(logging.DEBUG):
        run(conn.fetch(make_source()))
    blob = " ".join(r.getMessage() for r in caplog.records)
    assert "SECRET-123" not in blob and "Authorization" not in blob


# --- retries (65-69) ----------------------------------------------------- #
def test_non_retryable_4xx_not_retried(fast_retries) -> None:  # 65, 66
    calls = {"n": 0}
    def handler(request):
        calls["n"] += 1
        return httpx.Response(401, json={}, headers={"content-type": "application/json"})
    with pytest.raises(ApiIngestionError):
        run(make_connector(httpx.MockTransport(handler)).fetch(make_source()))
    assert calls["n"] == 1  # no retry on 4xx / auth failure


def test_transient_failure_retried_within_bound(fast_retries) -> None:  # 68
    calls = {"n": 0}
    def handler(request):
        calls["n"] += 1
        if calls["n"] <= 2:
            return httpx.Response(503, json={}, headers={"content-type": "application/json"})
        return httpx.Response(200, json=[{"a": 1}], headers={"content-type": "application/json"})
    result = run(make_connector(httpx.MockTransport(handler)).fetch(make_source()))
    assert result == [{"a": 1}]
    assert calls["n"] == 3  # 2 retries then success


def test_retries_are_finite(fast_retries) -> None:  # 69
    calls = {"n": 0}
    def handler(request):
        calls["n"] += 1
        return httpx.Response(500, json={}, headers={"content-type": "application/json"})
    with pytest.raises(ApiIngestionError):
        run(make_connector(httpx.MockTransport(handler)).fetch(make_source()))
    assert calls["n"] == 3  # max_retries(2) + 1, bounded
