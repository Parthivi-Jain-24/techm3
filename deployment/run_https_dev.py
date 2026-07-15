"""Deployment entrypoint: strict TLS 1.3 secure-demonstration listener (Phase 7).

Run from the repo root:  python deployment/run_https_dev.py

This is a NARROWLY-SCOPED LOCAL DEMONSTRATION of TLS 1.3 encryption in
transit — TLS is terminated directly by Uvicorn because this project has no
existing reverse-proxy/Nginx/Caddy/Docker infrastructure yet (see
docs/tls-in-transit.md for the architecture rationale). This script contains
no application/business logic — it only wires the certificate paths and the
strict TLS 1.3 SSLContext factory into Uvicorn's server.

Distinct from ordinary local development:
    HTTP  (no TLS)   : uvicorn app.main:app --reload   -> http://127.0.0.1:8000
    HTTPS (TLS 1.3)  : python deployment/run_https_dev.py -> https://localhost:8443

Fails CLOSED: if the certificate/key are missing, this exits with an error —
it never silently starts a plaintext listener instead.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running from the repo root without installing the backend package.
_BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(_BACKEND_DIR))

import uvicorn  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.tls import TLSConfigurationError, build_strict_tls13_context_factory  # noqa: E402


def main() -> None:
    try:
        ssl_context_factory = build_strict_tls13_context_factory()
    except TLSConfigurationError as exc:
        print(f"TLS secure mode cannot start: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    print(f"Starting strict TLS 1.3 demonstration listener on https://localhost:{settings.tls_port}")
    print("This listener REJECTS TLS 1.0/1.1/1.2 handshakes by design.")

    uvicorn.run(
        "app.main:app",
        app_dir=str(_BACKEND_DIR),
        host="127.0.0.1",
        port=settings.tls_port,
        ssl_certfile=str(settings.tls_cert_path),
        ssl_keyfile=str(settings.tls_key_path),
        ssl_context_factory=ssl_context_factory,
        # Only trusts forwarded headers from an explicitly configured proxy
        # boundary; empty (default) = trust none. See docs/tls-in-transit.md.
        forwarded_allow_ips=settings.trusted_proxy_ips or None,
        log_level="info",
    )


if __name__ == "__main__":
    main()
