# Owned by Workstream 1 (Secure Data Ingestion, Auth, Privacy, Database).
#
# Strict TLS 1.3 secure-demonstration profile (Phase 7).
#
# TLS is terminated by Uvicorn directly for this narrowly-scoped LOCAL
# demonstration — no reverse proxy/Nginx/Caddy/Docker infra exists yet in this
# project (see docs/tls-in-transit.md for why this is the smallest appropriate
# architecture). This module ONLY builds/validates the SSLContext; it contains
# no route or business logic, and it is not imported by app.main (the ordinary
# plain-HTTP dev server is completely unaffected by this module).
#
# Fails CLOSED: if the certificate/key are missing or invalid, secure mode
# refuses to start rather than silently falling back to plaintext HTTP.

from __future__ import annotations

import ssl
from pathlib import Path
from typing import Callable

from app.core.config import settings

# Fixed, not environment-configurable — this constant IS what makes the
# strict demonstration listener reject TLS 1.0/1.1/1.2, not merely "prefer"
# TLS 1.3. Weakening this would defeat the Phase 7 requirement.
STRICT_TLS_VERSION = ssl.TLSVersion.TLSv1_3


class TLSConfigurationError(Exception):
    """Secure TLS mode cannot start safely.

    Raised instead of ever falling back to an insecure plaintext listener.
    """


def validate_tls_paths() -> tuple[Path, Path]:
    """Confirm the configured certificate and key files exist.

    Raises ``TLSConfigurationError`` (fail closed) otherwise. Paths are
    externalized via ``settings.tls_cert_file`` / ``settings.tls_key_file`` —
    never hardcoded, never containing key material themselves.
    """
    cert = settings.tls_cert_path
    key = settings.tls_key_path
    if not cert.is_file():
        raise TLSConfigurationError(
            f"TLS certificate file not found: {cert}. "
            "Generate a local development certificate first "
            "(see scripts/setup/generate-dev-tls-cert.ps1 or docs/tls-in-transit.md)."
        )
    if not key.is_file():
        raise TLSConfigurationError(
            f"TLS private key file not found: {key}. "
            "Generate a local development certificate first "
            "(see scripts/setup/generate-dev-tls-cert.ps1 or docs/tls-in-transit.md)."
        )
    return cert, key


def build_strict_tls13_context_factory() -> Callable[
    [object, Callable[[], ssl.SSLContext]], ssl.SSLContext
]:
    """Return a uvicorn ``ssl_context_factory`` enforcing TLS 1.3 ONLY.

    Uvicorn calls this as ``factory(config, default_ssl_context_factory)``. We
    call the default factory (which loads the cert/key uvicorn was already
    configured with) and then explicitly pin both the minimum AND maximum
    negotiable protocol version to TLS 1.3, so TLS 1.0/1.1/1.2 handshakes are
    rejected by the TLS stack itself — not merely deprioritized.

    Validates cert/key presence up front (fail closed) before returning.
    """
    validate_tls_paths()

    def factory(
        config: object, default_ssl_context_factory: Callable[[], ssl.SSLContext]
    ) -> ssl.SSLContext:
        context = default_ssl_context_factory()
        context.minimum_version = STRICT_TLS_VERSION
        context.maximum_version = STRICT_TLS_VERSION
        return context

    return factory
