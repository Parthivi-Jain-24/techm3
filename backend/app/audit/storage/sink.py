"""Audit sink abstraction (Phase 9, PART M).

Mirrors the ``SecretProvider`` pattern from Phase 5/8: application code
depends on this narrow interface only, never on a concrete sink. This is the
seam that lets a future production deployment swap in a SIEM/WORM-forwarding
sink without touching ``AuditService`` or any call site.
"""

from __future__ import annotations

from typing import Protocol

from app.audit.events.models import AuditEvent


class AuditSink(Protocol):
    def write(self, event: AuditEvent) -> None:
        """Persist one audit event. Must not raise for the caller to rely on;
        ``AuditService`` treats any exception here as a sink failure and
        applies the documented failure policy (see PART Q / docs/audit-logging.md)."""
        ...
