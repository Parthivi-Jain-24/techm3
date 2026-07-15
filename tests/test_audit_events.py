"""Phase 9 tests: canonical AuditEvent schema, taxonomies, actor/resource models."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.audit.events.enums import ActorType, EventType, Outcome, Severity
from app.audit.events.models import ANONYMOUS_ACTOR, SYSTEM_ACTOR, Actor, AuditEvent, Resource


def _event(**overrides) -> AuditEvent:
    params = dict(
        event_type=EventType.HTTP_REQUEST,
        action="request.completed",
        outcome=Outcome.SUCCESS,
    )
    params.update(overrides)
    return AuditEvent(**params)


# --- event_id / timestamp (1-2) -------------------------------------------- #
def test_event_id_is_generated_and_unique() -> None:  # 1
    a, b = _event(), _event()
    assert a.event_id and b.event_id
    assert a.event_id != b.event_id


def test_timestamp_defaults_to_timezone_aware_utc() -> None:  # 2
    event = _event()
    assert event.timestamp.tzinfo is not None
    assert event.timestamp.tzinfo == timezone.utc or event.timestamp.utcoffset().total_seconds() == 0


def test_naive_timestamp_rejected() -> None:  # 2b
    with pytest.raises(ValidationError):
        _event(timestamp=datetime(2026, 1, 1))  # no tzinfo


def test_non_utc_timestamp_normalized_to_utc() -> None:
    from datetime import timedelta

    plus5 = timezone(timedelta(hours=5))
    event = _event(timestamp=datetime(2026, 1, 1, 10, 0, tzinfo=plus5))
    assert event.timestamp.tzinfo == timezone.utc
    assert event.timestamp.hour == 5


# --- event_type / outcome / severity taxonomies (3-5) ---------------------- #
def test_event_type_is_controlled() -> None:  # 3
    with pytest.raises(ValidationError):
        _event(event_type="NOT_A_REAL_TYPE")  # type: ignore[arg-type]
    assert _event(event_type=EventType.SECRET_ACCESS).event_type == EventType.SECRET_ACCESS


def test_outcome_is_controlled() -> None:  # 4
    with pytest.raises(ValidationError):
        _event(outcome="MAYBE")  # type: ignore[arg-type]
    assert _event(outcome=Outcome.DENIED).outcome == Outcome.DENIED


def test_severity_is_controlled_and_defaults_to_info() -> None:  # 5
    assert _event().severity == Severity.INFO
    with pytest.raises(ValidationError):
        _event(severity="SUPER_CRITICAL")  # type: ignore[arg-type]
    assert _event(severity=Severity.CRITICAL).severity == Severity.CRITICAL


# --- serialization / validation (6-7) --------------------------------------- #
def test_event_is_json_serializable() -> None:  # 6
    event = _event(
        actor=Actor(actor_id="U-1", actor_type=ActorType.USER, roles=("data_engineer",)),
        resource=Resource(resource_type="ingestion_source", resource_id="sample.csv"),
        request_id="11111111-1111-4111-8111-111111111111",
        duration_ms=12.5,
        metadata={"total_rows": 10},
    )
    payload = event.model_dump(mode="json")
    encoded = json.dumps(payload)  # must not raise
    decoded = json.loads(encoded)
    assert decoded["event_type"] == "HTTP_REQUEST"
    assert decoded["actor"]["actor_id"] == "U-1"
    assert isinstance(decoded["timestamp"], str)


def test_invalid_action_format_rejected() -> None:  # 7
    with pytest.raises(ValidationError):
        _event(action="not a stable machine name")
    with pytest.raises(ValidationError):
        _event(action="NoDotsNoLowercase")
    assert _event(action="ingestion.file.completed").action == "ingestion.file.completed"


def test_event_forbids_unknown_fields() -> None:  # 7b
    with pytest.raises(ValidationError):
        AuditEvent(
            event_type=EventType.HTTP_REQUEST,
            action="request.completed",
            outcome=Outcome.SUCCESS,
            unexpected_field="nope",
        )


def test_negative_duration_rejected() -> None:
    with pytest.raises(ValidationError):
        _event(duration_ms=-1.0)


def test_overlong_request_id_rejected() -> None:
    with pytest.raises(ValidationError):
        _event(request_id="x" * 65)


# --- Actor model (Part B) --------------------------------------------------- #
def test_actor_forbids_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        Actor(actor_id="U-1", actor_type=ActorType.USER, password="nope")  # type: ignore[call-arg]


def test_anonymous_and_system_actor_shapes() -> None:
    assert ANONYMOUS_ACTOR.actor_type == ActorType.ANONYMOUS
    assert ANONYMOUS_ACTOR.actor_id == "anonymous"
    assert SYSTEM_ACTOR.actor_type == ActorType.SYSTEM
    assert SYSTEM_ACTOR.actor_id == "system"
    assert ANONYMOUS_ACTOR != SYSTEM_ACTOR


def test_actor_roles_never_contain_credential_shaped_values() -> None:
    # Structural guarantee: Actor has no field for password/JWT/token at all.
    assert set(Actor.model_fields) == {"actor_id", "actor_type", "roles"}


# --- Resource model (Part C) ------------------------------------------------ #
def test_resource_type_must_be_snake_case() -> None:
    with pytest.raises(ValidationError):
        Resource(resource_type="Not Safe!")
    assert Resource(resource_type="secret_reference").resource_type == "secret_reference"


def test_resource_forbids_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        Resource(resource_type="secret_reference", secret_value="nope")  # type: ignore[call-arg]
