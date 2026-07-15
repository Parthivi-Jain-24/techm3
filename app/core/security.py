# Owned by Workstream 1 (Secure Data Ingestion, Auth, Privacy, Database).
#
# Minimal API security-header middleware. The authentication/JWT/RBAC primitives
# live under app/identity/ (Phase 4); this module only adds conservative
# response headers. No CORS is enabled (not required by an API-only backend).
#
# HSTS (Phase 7): applied ONLY when the request scheme is https, so ordinary
# localhost HTTP development (port 8000) is never affected. ``request.url.scheme``
# reflects the ASGI scope's scheme, which Uvicorn sets natively to "https" when
# TLS is terminated in-process (our secure demo mode) — no proxy-header trust
# is needed for this to work correctly in that mode. A conservative max-age is
# used (1 day); no includeSubDomains (no subdomain architecture exists to
# support it) and no preload (not submitted/eligible). HSTS does not itself
# encrypt anything — it only instructs compliant clients to prefer HTTPS for
# FUTURE requests to this host; TLS is what provides the encryption.

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# Conservative defaults appropriate for a JSON API.
_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
}

# 1 day — conservative for a demonstration profile. No includeSubDomains/preload.
_HSTS_HEADER_VALUE = "max-age=86400"


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Attach conservative security headers to every response.

    Adds ``Strict-Transport-Security`` only on responses actually served over
    HTTPS — never forced on plain HTTP localhost development.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        for header, value in _SECURITY_HEADERS.items():
            response.headers.setdefault(header, value)
        if request.url.scheme == "https":
            response.headers.setdefault("Strict-Transport-Security", _HSTS_HEADER_VALUE)
        return response
