"""Security audit-logging subsystem (Phase 9).

Distinct from ordinary application logging (``app.core.logging``): this
package answers WHO / WHAT ACTION / WHICH RESOURCE / WHEN / WHICH REQUEST /
WHAT OUTCOME for security- and governance-relevant events, as structured,
sanitized, correlated records -- not free-text diagnostic log lines. See
docs/audit-logging.md for the full architecture and the "audit logs vs
application logs" distinction.
"""

from app.audit.events import (
    ANONYMOUS_ACTOR,
    SYSTEM_ACTOR,
    Actor,
    ActorType,
    AuditEvent,
    EventType,
    Outcome,
    Resource,
    Severity,
)
from app.audit.middleware import AuditContextMiddleware
from app.audit.service import AuditService, get_audit_service

__all__ = [
    "AuditEvent",
    "Actor",
    "Resource",
    "EventType",
    "Outcome",
    "Severity",
    "ActorType",
    "ANONYMOUS_ACTOR",
    "SYSTEM_ACTOR",
    "AuditService",
    "get_audit_service",
    "AuditContextMiddleware",
]
