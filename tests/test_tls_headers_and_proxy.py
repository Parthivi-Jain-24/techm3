"""Phase 7 tests: HSTS header behavior, proxy-header trust boundary,
health/Swagger reachability under an HTTPS-scoped request.

Uses FastAPI's TestClient with an https:// base_url to represent an
HTTPS-scoped request (exactly what Uvicorn's ASGI scope looks like when TLS is
terminated in-process) — this avoids spinning up a real TLS listener /
privileged port in the automated unit-test suite (see docs/tls-in-transit.md
for the live manual verification procedure).
"""

from __future__ import annotations

import inspect

from fastapi.testclient import TestClient

from app.main import app

HTTPS_CLIENT = TestClient(app, base_url="https://testserver")
HTTP_CLIENT = TestClient(app, base_url="http://testserver")


# --- HSTS (17, 18, 19) ------------------------------------------------------ #
def test_hsts_present_on_https_response() -> None:  # 17
    r = HTTPS_CLIENT.get("/api/v1/health/live")
    assert "strict-transport-security" in {k.lower() for k in r.headers}
    assert "max-age=" in r.headers["strict-transport-security"]


def test_hsts_conservative_no_subdomains_no_preload() -> None:
    r = HTTPS_CLIENT.get("/api/v1/health/live")
    value = r.headers["strict-transport-security"]
    assert "includeSubDomains" not in value
    assert "preload" not in value


def test_hsts_not_forced_on_plain_http() -> None:  # 18
    r = HTTP_CLIENT.get("/api/v1/health/live")
    assert "strict-transport-security" not in {k.lower() for k in r.headers}


def test_other_security_headers_still_present_on_http() -> None:  # 19
    r = HTTP_CLIENT.get("/api/v1/health/live")
    assert r.headers.get("x-content-type-options") == "nosniff"
    assert r.headers.get("x-frame-options") == "DENY"
    assert r.status_code == 200  # security-header behavior doesn't break the API


def test_existing_api_behavior_unaffected_by_headers() -> None:  # 19
    r = HTTP_CLIENT.get("/api/v1/health/live")
    assert r.json() == {"status": "alive"}


# --- proxy-header trust boundary (13, 14) ----------------------------------- #
def test_default_trusted_proxy_ips_is_empty() -> None:  # trust nothing by default
    from app.core.config import settings

    assert settings.trusted_proxy_ips == ""


def test_trusted_proxy_ips_never_wildcarded_by_default() -> None:
    from app.core.config import settings

    assert settings.trusted_proxy_ips != "*"


def test_app_does_not_implement_its_own_forwarded_header_trust() -> None:  # 14
    # We rely on uvicorn's own forwarded_allow_ips boundary (configured only in
    # the deployment entrypoint, off by default) rather than the app reading
    # X-Forwarded-* headers itself — so there is no app-level code that could
    # blindly trust an arbitrary client-supplied header.
    import app.core.security as security_mod

    src = inspect.getsource(security_mod)
    assert "X-Forwarded" not in src


def test_arbitrary_client_forwarded_proto_header_is_not_trusted() -> None:  # 14
    # A client-supplied X-Forwarded-Proto must not change how OUR middleware
    # behaves; HSTS reflects the real ASGI-scope scheme, not a client header.
    r = HTTP_CLIENT.get(
        "/api/v1/health/live", headers={"X-Forwarded-Proto": "https"}
    )
    assert "strict-transport-security" not in {k.lower() for k in r.headers}


# --- health / docs reachability under HTTPS-scoped request (15, 16) -------- #
def test_health_reachable_under_https_scope() -> None:  # 15
    r = HTTPS_CLIENT.get("/api/v1/health/live")
    assert r.status_code == 200 and r.json() == {"status": "alive"}


def test_root_health_reachable_under_https_scope() -> None:  # 15
    assert HTTPS_CLIENT.get("/health").status_code == 200


def test_docs_reachable_under_https_scope() -> None:  # 16
    assert HTTPS_CLIENT.get("/docs").status_code == 200


def test_openapi_reachable_under_https_scope() -> None:  # 16
    assert HTTPS_CLIENT.get("/openapi.json").status_code == 200
