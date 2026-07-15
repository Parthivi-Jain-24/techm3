"""Audit event emission for Part 1's tamper-evident log (playbook §7, §10).

Part 2 *emits*; Part 1 *stores and hash-chains*. This module is the seam between
them: a sink protocol Part 1 implements, plus a default in-process sink so the
events are observable (and demoable) before Part 1's service exists.

Wiring, per playbook §7:
    ENTITY_MATCH_CALCULATED   — every match returned by the resolver
    ADVERSE_MEDIA_AGENT_RUN   — every adverse-media analysis
    PROMPT_INJECTION_DETECTED — every suspected injection

Swap in Part 1's real sink with `set_audit_sink(...)`.
"""

from __future__ import annotations

import hashlib
import json
import threading
from collections import deque
from datetime import datetime, timezone
from typing import Any, Protocol

from pydantic import BaseModel, Field

# Playbook §7 event names. Part 1 keys off these strings — do not rename.
ENTITY_MATCH_CALCULATED = "ENTITY_MATCH_CALCULATED"
ADVERSE_MEDIA_AGENT_RUN = "ADVERSE_MEDIA_AGENT_RUN"
PROMPT_INJECTION_DETECTED = "PROMPT_INJECTION_DETECTED"

# Part 2 is a service actor, not a human one.
ACTOR_TYPE = "AI_AGENT"
ACTOR_ID = "entity-intelligence-v1"

GENESIS_HASH = "0" * 64


class AuditEvent(BaseModel):
    """One auditable action, shaped per playbook §10.

    `previous_hash`/`event_hash` are populated by the sink, not the emitter — the
    chain is a property of the log's ordering, which only the sink knows.
    """

    event_id: str
    actor_type: str = ACTOR_TYPE
    actor_id: str = ACTOR_ID
    action: str
    resource: str
    old_value: Any = None
    new_value: Any = None
    reason: str | None = None
    timestamp: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)
    previous_hash: str | None = None
    event_hash: str | None = None

    def content_digest(self) -> str:
        """SHA-256 over the event's content and its predecessor's hash.

        Excludes `event_hash` itself (it is the output) but includes
        `previous_hash`, which is what chains entries together.
        """
        payload = self.model_dump(mode="json", exclude={"event_hash"})
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class AuditSink(Protocol):
    """What Part 1 implements to receive Part 2's events."""

    def write(self, event: AuditEvent) -> AuditEvent: ...


class InMemoryAuditSink:
    """Default sink: append-only, hash-chained, bounded.

    Stands in for Part 1's service so events are observable end-to-end before it
    exists. Bounded because screening emits per match and this must never grow
    without limit in a long-running process — `dropped` records what fell off so
    a truncated view is never mistaken for the whole history.
    """

    def __init__(self, maxlen: int = 10_000) -> None:
        self._events: deque[AuditEvent] = deque(maxlen=maxlen)
        self._lock = threading.Lock()
        self._counter = 0
        self._last_hash = GENESIS_HASH
        self.dropped = 0

    def write(self, event: AuditEvent) -> AuditEvent:
        with self._lock:
            event.previous_hash = self._last_hash
            event.event_hash = event.content_digest()
            self._last_hash = event.event_hash

            if len(self._events) == self._events.maxlen:
                self.dropped += 1
            self._events.append(event)
            self._counter += 1
            return event

    def events(self, limit: int | None = None) -> list[AuditEvent]:
        with self._lock:
            items = list(self._events)
        return items[-limit:] if limit else items

    def verify_chain(self) -> dict[str, Any]:
        """Recompute every hash and report the first break.

        Only meaningful over the retained window: entries evicted by `maxlen`
        take their links with them, so verification starts at the oldest
        retained event rather than at genesis.
        """
        with self._lock:
            items = list(self._events)

        if not items:
            return {"valid": True, "events_checked": 0, "broken_at": None,
                    "verified_from_genesis": True}

        previous = GENESIS_HASH if self.dropped == 0 else items[0].previous_hash
        for index, event in enumerate(items):
            if event.previous_hash != previous:
                return {"valid": False, "events_checked": index + 1,
                        "broken_at": event.event_id, "reason": "previous_hash mismatch",
                        "verified_from_genesis": self.dropped == 0}
            if event.content_digest() != event.event_hash:
                return {"valid": False, "events_checked": index + 1,
                        "broken_at": event.event_id, "reason": "content altered",
                        "verified_from_genesis": self.dropped == 0}
            previous = event.event_hash

        return {"valid": True, "events_checked": len(items), "broken_at": None,
                "verified_from_genesis": self.dropped == 0}

    @property
    def count(self) -> int:
        return self._counter

    def next_event_id(self) -> str:
        with self._lock:
            return f"AUD-{self._counter + 1:05d}"

    def reset(self) -> None:
        with self._lock:
            self._events.clear()
            self._counter = 0
            self._last_hash = GENESIS_HASH
            self.dropped = 0


_sink: AuditSink = InMemoryAuditSink()
_sink_lock = threading.Lock()


def set_audit_sink(sink: AuditSink) -> None:
    """Point Part 2's events at Part 1's log."""
    global _sink
    with _sink_lock:
        _sink = sink


def get_audit_sink() -> AuditSink:
    return _sink


def emit(
    action: str,
    resource: str,
    *,
    reason: str | None = None,
    old_value: Any = None,
    new_value: Any = None,
    metadata: dict[str, Any] | None = None,
) -> AuditEvent:
    """Record one auditable action. Never raises into the caller's path.

    An audit sink failing must not take screening down with it — a dropped event
    is a reporting problem, an exception here would be an outage.
    """
    sink = _sink
    event_id = (
        sink.next_event_id() if isinstance(sink, InMemoryAuditSink)
        else f"AUD-{datetime.now(timezone.utc).timestamp():.6f}"
    )
    event = AuditEvent(
        event_id=event_id,
        action=action,
        resource=resource,
        reason=reason,
        old_value=old_value,
        new_value=new_value,
        timestamp=datetime.now(timezone.utc),
        metadata=metadata or {},
    )
    try:
        return sink.write(event)
    except Exception:  # noqa: BLE001 - audit must never break the caller
        return event
