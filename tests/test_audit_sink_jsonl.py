"""Phase 9 tests: HashChainedJsonLinesAuditSink, safe path handling, and the
offline verification tool. All file I/O uses pytest's ``tmp_path`` -- never
the real backend/var/audit/ directory (see conftest.py's autouse
``_isolate_audit_sink`` fixture for why other test files don't need this)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from app.audit.events.enums import EventType, Outcome
from app.audit.events.models import AuditEvent
from app.audit.storage.hashchain import GENESIS_HASH, canonical_json
from app.audit.storage.jsonl import HashChainedJsonLinesAuditSink
from app.audit.verify import verify_chain


def _event(**overrides) -> AuditEvent:
    params = dict(event_type=EventType.HTTP_REQUEST, action="request.completed", outcome=Outcome.SUCCESS)
    params.update(overrides)
    return AuditEvent(**params)


# --- basic JSONL behavior (71-75) ------------------------------------------- #
def test_one_event_per_line_valid_json_utf8(tmp_path) -> None:  # 71, 72, 73
    path = tmp_path / "audit.jsonl"
    sink = HashChainedJsonLinesAuditSink(path)
    sink.write(_event())
    sink.write(_event(metadata={"unicode": "café ☂ 日本語"}))
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    for line in lines:
        obj = json.loads(line)  # must not raise
        assert isinstance(obj, dict)
    assert "\n" not in lines[0]  # single line, never pretty-printed


def test_parent_directory_created_safely(tmp_path) -> None:  # 75
    path = tmp_path / "nested" / "deeper" / "audit.jsonl"
    sink = HashChainedJsonLinesAuditSink(path)
    sink.write(_event())
    assert path.exists()


def test_server_controlled_path_resolution(monkeypatch) -> None:  # 74
    from app.audit.storage.paths import AUDIT_RUNTIME_DIR, resolve_audit_log_path
    from app.core.config import settings

    monkeypatch.setattr(settings, "audit_log_path", "backend/var/audit/audit.jsonl")
    resolved = resolve_audit_log_path()
    assert resolved.resolve().is_relative_to(AUDIT_RUNTIME_DIR.resolve())


def test_path_traversal_falls_back_to_approved_default(monkeypatch) -> None:  # 74b (defense in depth)
    from app.audit.storage.paths import AUDIT_RUNTIME_DIR, resolve_audit_log_path
    from app.core.config import settings

    monkeypatch.setattr(settings, "audit_log_path", "../../../etc/passwd")
    resolved = resolve_audit_log_path()
    assert resolved.resolve().is_relative_to(AUDIT_RUNTIME_DIR.resolve())


def test_runtime_audit_directory_is_git_ignored() -> None:  # 76 (mirrors test_tls_config.py)
    from app.core.config import PROJECT_ROOT

    # `git check-ignore` evaluates the ignore rules for a path without creating
    # it, and exits 0 only when the path is ignored.
    #
    # This deliberately does NOT write a probe file: the runtime log is the real
    # audit trail of any server running against this checkout, and a test that
    # writes then unlinks it would silently destroy live audit evidence. (The
    # earlier version did exactly that; it went unnoticed only because a
    # PROJECT_ROOT bug pointed the path outside the repository entirely.)
    result = subprocess.run(
        ["git", "-C", str(PROJECT_ROOT), "check-ignore", "-v", "backend/var/audit/audit.jsonl"],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, (
        "backend/var/audit/audit.jsonl is not git-ignored: runtime audit output "
        f"could be committed. git said: {result.stdout or result.stderr!r}"
    )
    assert "backend/var/audit" in result.stdout.replace("\\", "/")


# --- sink failure policy (77-78) --------------------------------------------- #
def test_sink_write_failure_does_not_raise_from_audit_service(tmp_path, caplog) -> None:  # 77, 78
    from app.audit.service import AuditService

    class ExplodingSink:
        def write(self, event: AuditEvent) -> None:
            raise OSError("disk full (simulated)")

    svc = AuditService(ExplodingSink())
    import logging

    with caplog.at_level(logging.ERROR, logger="app.audit"):
        result = svc.emit(event_type=EventType.HTTP_REQUEST, action="request.completed", outcome=Outcome.SUCCESS)
    assert result is not None  # event was still constructed
    assert any("audit sink write failed" in r.message for r in caplog.records)


# --- hash chain (79-86) ------------------------------------------------------- #
def test_first_event_uses_genesis_previous_hash(tmp_path) -> None:  # 79
    path = tmp_path / "audit.jsonl"
    sink = HashChainedJsonLinesAuditSink(path)
    sink.write(_event())
    obj = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert obj["previous_hash"] == GENESIS_HASH


def test_second_event_references_first_event_hash(tmp_path) -> None:  # 80
    path = tmp_path / "audit.jsonl"
    sink = HashChainedJsonLinesAuditSink(path)
    sink.write(_event())
    sink.write(_event())
    lines = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()]
    assert lines[1]["previous_hash"] == lines[0]["event_hash"]


def test_canonical_json_is_deterministic_regardless_of_key_order() -> None:  # 81
    a = canonical_json({"b": 1, "a": 2})
    b = canonical_json({"a": 2, "b": 1})
    assert a == b


def test_valid_chain_verifies_successfully(tmp_path) -> None:  # 82
    path = tmp_path / "audit.jsonl"
    sink = HashChainedJsonLinesAuditSink(path)
    for _ in range(5):
        sink.write(_event())
    result = verify_chain(path)
    assert result.valid is True
    assert result.lines_checked == 5


def test_modified_event_is_detected(tmp_path) -> None:  # 83
    path = tmp_path / "audit.jsonl"
    sink = HashChainedJsonLinesAuditSink(path)
    sink.write(_event())
    sink.write(_event(metadata={"status_code": 200}))
    lines = path.read_text(encoding="utf-8").splitlines()
    obj = json.loads(lines[1])
    obj["metadata"] = {"status_code": 999}  # tamper, without recomputing hash
    lines[1] = json.dumps(obj, sort_keys=True, separators=(",", ":"))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    result = verify_chain(path)
    assert result.valid is False
    assert result.failed_line == 2
    assert "content modified" in result.reason


def test_reordered_events_detected(tmp_path) -> None:  # 84
    path = tmp_path / "audit.jsonl"
    sink = HashChainedJsonLinesAuditSink(path)
    sink.write(_event())
    sink.write(_event())
    lines = path.read_text(encoding="utf-8").splitlines()
    lines[0], lines[1] = lines[1], lines[0]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    result = verify_chain(path)
    assert result.valid is False
    assert result.failed_line == 1


def test_broken_previous_hash_detected(tmp_path) -> None:  # 85
    path = tmp_path / "audit.jsonl"
    sink = HashChainedJsonLinesAuditSink(path)
    sink.write(_event())
    lines = path.read_text(encoding="utf-8").splitlines()
    obj = json.loads(lines[0])
    obj["previous_hash"] = "f" * 64  # break the link without recomputing hash
    path.write_text(json.dumps(obj, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")

    result = verify_chain(path)
    assert result.valid is False
    assert result.failed_line == 1
    assert "broken previous_hash" in result.reason


def test_verify_cli_does_not_print_sensitive_event_content(tmp_path) -> None:  # 86
    from app.audit.events.enums import EventType, Outcome
    from app.audit.events.models import Actor, Resource
    from app.audit.events.enums import ActorType
    from app.audit.events.resources import SECRET_REFERENCE

    path = tmp_path / "audit.jsonl"
    sink = HashChainedJsonLinesAuditSink(path)
    sink.write(
        _event(
            actor=Actor(actor_id="U-SENSITIVE-ID-777", actor_type=ActorType.USER),
            resource=Resource(resource_type=SECRET_REFERENCE, resource_id="my-secret-name"),
        )
    )
    proc = subprocess.run(
        [sys.executable, "-m", "app.audit.verify", str(path)],
        cwd=str(Path(__file__).resolve().parents[1]),
        capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0
    assert "U-SENSITIVE-ID-777" not in proc.stdout
    assert "my-secret-name" not in proc.stdout
    assert "VALID chain" in proc.stdout


def test_verify_cli_reports_invalid_chain_with_exit_code_1(tmp_path) -> None:
    path = tmp_path / "audit.jsonl"
    sink = HashChainedJsonLinesAuditSink(path)
    sink.write(_event())
    lines = path.read_text(encoding="utf-8").splitlines()
    obj = json.loads(lines[0])
    obj["event_hash"] = "0" * 64
    path.write_text(json.dumps(obj, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")

    proc = subprocess.run(
        [sys.executable, "-m", "app.audit.verify", str(path)],
        cwd=str(Path(__file__).resolve().parents[1]),
        capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 1
    assert "INVALID chain" in proc.stdout
