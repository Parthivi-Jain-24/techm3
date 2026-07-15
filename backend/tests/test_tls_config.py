"""Phase 7 tests: strict TLS 1.3 configuration (static — no live server/port)."""

from __future__ import annotations

import inspect
import ssl

import pytest

from app.core.tls import (
    STRICT_TLS_VERSION,
    TLSConfigurationError,
    build_strict_tls13_context_factory,
    validate_tls_paths,
)
from tests._tls_helpers import write_test_cert_pair


# --- configuration (1-9) --------------------------------------------------- #
def test_secure_tls_configuration_exists() -> None:  # 1
    import app.core.tls as tls_mod

    assert hasattr(tls_mod, "build_strict_tls13_context_factory")


def test_strict_profile_requires_tls13() -> None:  # 2
    assert STRICT_TLS_VERSION == ssl.TLSVersion.TLSv1_3


def test_tls10_not_enabled_in_strict_profile(tmp_path, monkeypatch) -> None:  # 3
    cert, key = write_test_cert_pair(tmp_path)
    _patch_settings(monkeypatch, cert, key)
    factory = build_strict_tls13_context_factory()
    context = factory(None, lambda: _base_server_context(cert, key))
    assert context.minimum_version == ssl.TLSVersion.TLSv1_3
    # A minimum of TLSv1_3 mathematically excludes TLSv1 (and everything below).
    assert ssl.TLSVersion.TLSv1 < context.minimum_version


def test_tls11_not_enabled_in_strict_profile(tmp_path, monkeypatch) -> None:  # 4
    cert, key = write_test_cert_pair(tmp_path)
    _patch_settings(monkeypatch, cert, key)
    factory = build_strict_tls13_context_factory()
    context = factory(None, lambda: _base_server_context(cert, key))
    assert ssl.TLSVersion.TLSv1_1 < context.minimum_version


def test_tls12_not_enabled_in_strict_profile(tmp_path, monkeypatch) -> None:  # 5
    cert, key = write_test_cert_pair(tmp_path)
    _patch_settings(monkeypatch, cert, key)
    factory = build_strict_tls13_context_factory()
    context = factory(None, lambda: _base_server_context(cert, key))
    assert context.minimum_version == ssl.TLSVersion.TLSv1_3
    assert context.maximum_version == ssl.TLSVersion.TLSv1_3
    assert ssl.TLSVersion.TLSv1_2 < context.minimum_version  # TLS 1.2 excluded


def test_certificate_path_is_externalized() -> None:  # 6
    from app.core.config import settings

    assert isinstance(settings.tls_cert_file, str)
    assert settings.tls_cert_file  # configurable, not hardcoded in tls.py
    src = inspect.getsource(__import__("app.core.tls", fromlist=["*"]))
    assert '"certs/' not in src and "'certs/" not in src  # no hardcoded path


def test_private_key_path_is_externalized() -> None:  # 7
    from app.core.config import settings

    assert isinstance(settings.tls_key_file, str)
    assert settings.tls_key_file


def test_no_real_private_key_committed() -> None:  # 8
    import subprocess

    from app.core.config import PROJECT_ROOT

    result = subprocess.run(
        ["git", "-C", str(PROJECT_ROOT), "ls-files", "certs/"],
        capture_output=True, text=True, check=False,
    )
    tracked = [line for line in result.stdout.splitlines() if line.strip()]
    assert tracked == []  # nothing under certs/ is tracked by git


def test_missing_cert_fails_closed_not_silent_http_fallback(tmp_path, monkeypatch) -> None:  # 9
    from app.core.config import settings

    monkeypatch.setattr(settings, "tls_cert_file", str(tmp_path / "does-not-exist-cert.pem"))
    monkeypatch.setattr(settings, "tls_key_file", str(tmp_path / "does-not-exist-key.pem"))
    with pytest.raises(TLSConfigurationError):
        build_strict_tls13_context_factory()


def test_missing_key_fails_closed(tmp_path, monkeypatch) -> None:
    cert, _ = write_test_cert_pair(tmp_path)
    from app.core.config import settings

    monkeypatch.setattr(settings, "tls_cert_file", str(cert))
    monkeypatch.setattr(settings, "tls_key_file", str(tmp_path / "missing-key.pem"))
    with pytest.raises(TLSConfigurationError):
        validate_tls_paths()


def test_valid_paths_pass_validation(tmp_path, monkeypatch) -> None:
    cert, key = write_test_cert_pair(tmp_path)
    _patch_settings(monkeypatch, cert, key)
    resolved_cert, resolved_key = validate_tls_paths()
    assert resolved_cert.is_file() and resolved_key.is_file()


# --- outbound TLS regression (20-23) --------------------------------------- #
def test_outbound_https_still_required() -> None:  # 20
    from app.ingestion.api.errors import ApiIngestionError
    from app.ingestion.api.security import validate_destination

    with pytest.raises(ApiIngestionError):
        validate_destination("http://external-api.example.com/data", resolve=lambda h: ["93.184.216.34"])


def test_outbound_certificate_verification_not_disabled() -> None:  # 21, 22
    # Check actual code lines, not comments that merely (correctly) state the
    # policy — split out lines starting with '#' before searching for the
    # literal kwarg assignment pattern.
    import app.ingestion.api.client as client_mod

    code_lines = [
        line for line in inspect.getsource(client_mod).splitlines()
        if not line.strip().startswith("#")
    ]
    code_only = "\n".join(code_lines)
    assert "verify=False" not in code_only
    assert "verify = False" not in code_only


def test_no_tls_warning_suppression_introduced() -> None:  # 23
    import app.ingestion.api.client as client_mod

    src = inspect.getsource(client_mod)
    assert "disable_warnings" not in src
    assert "InsecureRequestWarning" not in src


# --- helpers ---------------------------------------------------------------- #
def _patch_settings(monkeypatch, cert, key) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "tls_cert_file", str(cert))
    monkeypatch.setattr(settings, "tls_key_file", str(key))


def _base_server_context(cert, key) -> ssl.SSLContext:
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certfile=str(cert), keyfile=str(key))
    return context
