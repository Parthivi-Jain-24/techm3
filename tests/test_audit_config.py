"""Phase 9 tests: AuditService sink selection / fail-safe configuration handling."""

from __future__ import annotations

import logging

from app.audit.service import _build_default_sink, get_audit_service, reset_audit_service
from app.audit.storage.memory import InMemoryAuditSink, NullAuditSink


def test_disabled_audit_uses_null_sink(monkeypatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "audit_enabled", False)
    sink = _build_default_sink()
    assert isinstance(sink, NullAuditSink)


def test_memory_sink_selected_when_configured(monkeypatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "audit_enabled", True)
    monkeypatch.setattr(settings, "audit_sink", "memory")
    sink = _build_default_sink()
    assert isinstance(sink, InMemoryAuditSink)


def test_invalid_sink_name_falls_back_to_null_without_crashing(monkeypatch, caplog) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "audit_enabled", True)
    monkeypatch.setattr(settings, "audit_sink", "kafka")  # not supported
    with caplog.at_level(logging.ERROR, logger="app.audit"):
        sink = _build_default_sink()
    assert isinstance(sink, NullAuditSink)
    assert any("invalid AUDIT_SINK" in r.message for r in caplog.records)


def test_get_audit_service_is_a_singleton_until_reset() -> None:
    reset_audit_service()
    try:
        a = get_audit_service()
        b = get_audit_service()
        assert a is b
        reset_audit_service()
        c = get_audit_service()
        assert c is not a
    finally:
        reset_audit_service()


def test_jsonl_sink_construction_failure_falls_back_to_null(monkeypatch, tmp_path) -> None:
    from app.core.config import settings

    # Point at a path whose parent cannot be created (a file, not a directory,
    # sitting where a directory is expected) to force an OSError.
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory", encoding="utf-8")
    monkeypatch.setattr(settings, "audit_enabled", True)
    monkeypatch.setattr(settings, "audit_sink", "jsonl")

    from app.audit.storage import paths as paths_mod

    monkeypatch.setattr(
        paths_mod, "resolve_audit_log_path", lambda: blocker / "sub" / "audit.jsonl"
    )
    monkeypatch.setattr(
        "app.audit.service.resolve_audit_log_path", lambda: blocker / "sub" / "audit.jsonl"
    )
    sink = _build_default_sink()
    assert isinstance(sink, NullAuditSink)
