"""In-memory audit sinks (Phase 9): tests and the disabled/no-op default."""

from __future__ import annotations

import threading

from app.audit.events.models import AuditEvent


class InMemoryAuditSink:
    """Collects events in a list. Test-only -- never used in production config."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.events: list[AuditEvent] = []

    def write(self, event: AuditEvent) -> None:
        with self._lock:
            self.events.append(event)

    def clear(self) -> None:
        with self._lock:
            self.events.clear()


class NullAuditSink:
    """Discards events. Used when ``AUDIT_ENABLED=false`` or as a fail-safe
    fallback if the configured sink cannot be constructed (see
    ``app.audit.service._build_default_sink``)."""

    def write(self, event: AuditEvent) -> None:  # noqa: D401 - intentional no-op
        return None
