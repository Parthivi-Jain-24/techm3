"""Phase 9 tests: AuditContextMiddleware (PART E/F/U/V/W).

Uses the autouse ``_isolate_audit_sink`` fixture from conftest.py, which
replaces the process-wide AuditService with one backed by an
``InMemoryAuditSink`` -- so these tests inspect real events emitted through
the real middleware/app, without touching the filesystem.
"""

from __future__ import annotations

import uuid

from app.audit.events.enums import Outcome, Severity
from app.audit.middleware.asgi import _outcome_for_status, _severity_for_status

SYNTHETIC_QUERY_TOKEN = "SYNTHETIC_QUERY_TOKEN_DO_NOT_LOG_888"
SYNTHETIC_BODY_SECRET = "SYNTHETIC_BODY_SECRET_DO_NOT_LOG_777"


def _completion_events(sink):
    return [e for e in sink.events if e.action == "request.completed"]


# --- middleware / request lifecycle (15-23) --------------------------------- #
def test_successful_request_creates_completion_event(client, _isolate_audit_sink) -> None:  # 15
    r = client.get("/api/v1/health/live")
    assert r.status_code == 200
    events = _completion_events(_isolate_audit_sink)
    assert len(events) == 1
    assert events[0].outcome == Outcome.SUCCESS
    assert events[0].metadata["status_code"] == 200


def test_4xx_outcome_classified_correctly(client, _isolate_audit_sink) -> None:  # 16
    r = client.get("/api/v1/does-not-exist")
    assert r.status_code == 404
    events = _completion_events(_isolate_audit_sink)
    assert events[-1].outcome == Outcome.FAILURE


def test_401_classified_as_denied(client, _isolate_audit_sink) -> None:  # 16b
    r = client.post("/api/v1/ingestion/api/whatever/run")
    assert r.status_code == 401
    events = _completion_events(_isolate_audit_sink)
    assert events[-1].outcome == Outcome.DENIED


def test_outcome_and_severity_status_mapping_unit() -> None:  # 17
    assert _outcome_for_status(200) == Outcome.SUCCESS
    assert _outcome_for_status(401) == Outcome.DENIED
    assert _outcome_for_status(403) == Outcome.DENIED
    assert _outcome_for_status(404) == Outcome.FAILURE
    assert _outcome_for_status(500) == Outcome.ERROR
    assert _outcome_for_status(None) == Outcome.ERROR
    assert _severity_for_status(500) == Severity.ERROR
    assert _severity_for_status(404) == Severity.WARNING
    assert _severity_for_status(200) == Severity.INFO


def test_duration_is_recorded(client, _isolate_audit_sink) -> None:  # 18
    client.get("/api/v1/health/live")
    event = _completion_events(_isolate_audit_sink)[-1]
    assert event.duration_ms is not None
    assert event.duration_ms >= 0


def test_query_string_not_logged(client, _isolate_audit_sink) -> None:  # 19
    r = client.get(f"/api/v1/health/live?token={SYNTHETIC_QUERY_TOKEN}")
    assert r.status_code == 200
    event = _completion_events(_isolate_audit_sink)[-1]
    dumped = event.model_dump_json()
    assert SYNTHETIC_QUERY_TOKEN not in dumped
    assert "token=" not in dumped
    assert event.resource is not None and "?" not in (event.resource.resource_id or "")


def test_request_body_not_logged(client, _isolate_audit_sink) -> None:  # 20
    r = client.post(
        "/api/v1/auth/token",
        data={"username": "nope", "password": SYNTHETIC_BODY_SECRET},
    )
    assert r.status_code in (401, 422)
    dumped = "".join(e.model_dump_json() for e in _isolate_audit_sink.events)
    assert SYNTHETIC_BODY_SECRET not in dumped


def test_response_body_never_embedded_in_audit_event(client, _isolate_audit_sink) -> None:  # 21
    r = client.get("/api/v1/health/live")
    body_text = r.text
    event = _completion_events(_isolate_audit_sink)[-1]
    dumped = event.model_dump_json()
    # The event only records status_code/method -- not the response payload.
    assert set(event.metadata.keys()) == {"method", "status_code"}
    assert body_text not in dumped or body_text == ""  # trivially true either way


def test_health_endpoint_behavior_remains_intact(client) -> None:  # 22
    r = client.get("/api/v1/health/live")
    assert r.status_code == 200
    assert r.json() == {"status": "alive"}


def test_middleware_returns_x_request_id_header(client) -> None:  # 17 (PART W)
    r = client.get("/api/v1/health/live")
    rid = r.headers.get("x-request-id")
    assert rid is not None
    assert uuid.UUID(rid)


def test_incoming_request_id_is_correlated_into_event(client, _isolate_audit_sink) -> None:  # 14
    incoming = str(uuid.uuid4())
    r = client.get("/api/v1/health/live", headers={"X-Request-ID": incoming})
    assert r.headers["x-request-id"] == incoming
    event = _completion_events(_isolate_audit_sink)[-1]
    assert event.request_id == incoming
