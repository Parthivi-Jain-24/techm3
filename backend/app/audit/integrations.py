"""Small shared helpers for domain audit integrations (Phase 9).

Kept here (rather than duplicated at each call site) so the two secret-access
call sites -- ``app.encryption.keys.resolve_key`` and
``app.ingestion.api.client.ApiConnector._auth_headers`` -- stay consistent.
This module does NOT import ``app.secrets`` (only duck-types on
``type(provider).__name__``), so there is no import-cycle risk and, more
importantly, no possibility of this module ever needing to itself resolve a
secret to do its job (PART L: no audit-recursion).
"""

from __future__ import annotations

from typing import Any

from app.audit.events.actions import SECRET_ACCESS_FAILED, SECRET_ACCESS_SUCCEEDED
from app.audit.events.enums import EventType, Outcome, Severity
from app.audit.events.models import Resource
from app.audit.events.resources import SECRET_REFERENCE
from app.audit.service import get_audit_service


def audit_secret_access(provider: Any, logical_name: str, *, success: bool) -> None:
    """Record a SECRET_ACCESS event. ``logical_name`` is a non-secret logical
    identifier (e.g. an encryption ``key_id`` or an API ``auth_secret_name``)
    -- the Phase 5/6/8 architecture already treats these as safe metadata,
    never the secret value itself (which this function never receives)."""
    get_audit_service().emit(
        event_type=EventType.SECRET_ACCESS,
        action=SECRET_ACCESS_SUCCEEDED if success else SECRET_ACCESS_FAILED,
        outcome=Outcome.SUCCESS if success else Outcome.FAILURE,
        severity=Severity.INFO if success else Severity.WARNING,
        resource=Resource(resource_type=SECRET_REFERENCE, resource_id=logical_name or None),
        metadata={"provider_type": type(provider).__name__},
    )
