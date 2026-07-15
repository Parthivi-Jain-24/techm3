"""Central audit emitter (Phase 9, PART Y).

Every audit event in the codebase is created by calling
``get_audit_service().emit(...)`` -- nowhere else constructs an
``AuditEvent`` or writes directly to a sink. That single choke point is what
makes centralized sanitization (PART R) and the fail-safe write policy
(PART Q) actually centralized, instead of a convention every call site has
to remember independently.

This module is intentionally the ONLY place ``settings.audit_sink`` /
``settings.audit_log_path`` are interpreted (mirrors
``app.secrets.factory.resolve_secret_provider`` for the same reason).
"""

from __future__ import annotations

import logging
from typing import Any

from app.audit.events.enums import EventType, Outcome, Severity
from app.audit.events.models import AuditEvent, Resource
from app.audit.events.sanitize import sanitize_metadata
from app.audit.middleware.context import current_actor, current_request_id
from app.audit.storage.jsonl import HashChainedJsonLinesAuditSink
from app.audit.storage.memory import NullAuditSink
from app.audit.storage.paths import resolve_audit_log_path
from app.audit.storage.sink import AuditSink
from app.core.config import settings

# Deliberately the ORDINARY application logger, never the audit sink itself
# -- this is how sink-write failures get reported without any risk of
# recursing back into a failed sink (PART Q).
_fallback_logger = logging.getLogger("app.audit")

SUPPORTED_SINKS = frozenset({"jsonl", "memory", "null"})


class AuditService:
    def __init__(self, sink: AuditSink) -> None:
        self._sink = sink

    def emit(
        self,
        *,
        event_type: EventType,
        action: str,
        outcome: Outcome,
        severity: Severity = Severity.INFO,
        actor: Any | None = None,
        resource: Resource | None = None,
        request_id: str | None = None,
        duration_ms: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AuditEvent | None:
        """Build, sanitize, and persist one audit event. Never raises --
        construction or sink-write failures are reported via the ordinary
        application logger and the caller's primary operation proceeds
        unaffected (fail-safe, see docs/audit-logging.md "Sink failure
        policy"). Returns ``None`` only if event construction itself failed."""
        try:
            resolved_actor = actor if actor is not None else current_actor()
            resolved_request_id = request_id if request_id is not None else current_request_id()
            event = AuditEvent(
                event_type=event_type,
                action=action,
                outcome=outcome,
                severity=severity,
                request_id=resolved_request_id,
                actor=resolved_actor,
                resource=resource,
                duration_ms=duration_ms,
                metadata=sanitize_metadata(metadata),
            )
        except Exception:  # noqa: BLE001 - never break the caller's real operation
            _fallback_logger.error(
                "audit event construction failed action=%s event_type=%s",
                action,
                getattr(event_type, "value", event_type),
            )
            return None

        try:
            self._sink.write(event)
        except Exception:  # noqa: BLE001 - see PART Q: report, don't crash, don't recurse
            _fallback_logger.error(
                "audit sink write failed action=%s event_type=%s outcome=%s",
                event.action,
                event.event_type.value,
                event.outcome.value,
            )
        return event


_default_service: AuditService | None = None


def _build_default_sink() -> AuditSink:
    if not settings.audit_enabled:
        return NullAuditSink()

    name = (settings.audit_sink or "").strip().lower()
    if name not in SUPPORTED_SINKS:
        _fallback_logger.error(
            "invalid AUDIT_SINK=%r (expected one of %s) -- disabling audit writes",
            settings.audit_sink,
            sorted(SUPPORTED_SINKS),
        )
        return NullAuditSink()

    if name == "null":
        return NullAuditSink()
    if name == "memory":
        from app.audit.storage.memory import InMemoryAuditSink

        return InMemoryAuditSink()

    # name == "jsonl" -- the production-shaped local default.
    try:
        return HashChainedJsonLinesAuditSink(resolve_audit_log_path())
    except OSError:
        # Fail-safe: an unavailable runtime directory/disk must not prevent
        # the application from starting or serving requests (PART Q).
        _fallback_logger.error(
            "could not initialize JSONL audit sink at %s -- disabling audit writes",
            settings.audit_log_path,
        )
        return NullAuditSink()


def get_audit_service() -> AuditService:
    """Process-wide ``AuditService`` singleton, built from configuration."""
    global _default_service
    if _default_service is None:
        _default_service = AuditService(_build_default_sink())
    return _default_service


def set_audit_service(service: AuditService) -> None:
    """Test-only: inject a service (e.g. backed by ``InMemoryAuditSink``)."""
    global _default_service
    _default_service = service


def reset_audit_service() -> None:
    """Test-only: clear the cached singleton so the next call rebuilds it
    from current settings (mirrors ``app.secrets.factory.reset_provider_cache``)."""
    global _default_service
    _default_service = None
