"""Phase 9 tests: request-ID generation and strict validation (PART D)."""

from __future__ import annotations

import uuid

from app.audit.middleware.request_id import (
    MAX_REQUEST_ID_LENGTH,
    generate_request_id,
    resolve_request_id,
)


def test_missing_request_id_generates_valid_uuid() -> None:  # 8
    rid = resolve_request_id(None)
    assert uuid.UUID(rid)


def test_empty_request_id_generates_valid_uuid() -> None:  # 8b
    rid = resolve_request_id("")
    assert uuid.UUID(rid)


def test_valid_incoming_uuid_is_preserved() -> None:  # 9
    incoming = str(uuid.uuid4())
    assert resolve_request_id(incoming) == incoming


def test_malformed_request_id_is_replaced() -> None:  # 10
    rid = resolve_request_id("not-a-uuid-at-all")
    assert uuid.UUID(rid)
    assert rid != "not-a-uuid-at-all"


def test_overlong_request_id_is_replaced() -> None:  # 11
    overlong = "a" * (MAX_REQUEST_ID_LENGTH + 100)
    rid = resolve_request_id(overlong)
    assert uuid.UUID(rid)
    assert len(rid) < len(overlong)


def test_control_character_request_id_is_replaced() -> None:  # 12
    malicious = str(uuid.uuid4()) + "\r\nX-Injected: evil"
    rid = resolve_request_id(malicious)
    assert uuid.UUID(rid)
    assert "\r" not in rid and "\n" not in rid
    assert "Injected" not in rid


def test_generate_request_id_produces_unique_values() -> None:
    a, b = generate_request_id(), generate_request_id()
    assert a != b
    assert uuid.UUID(a) and uuid.UUID(b)
