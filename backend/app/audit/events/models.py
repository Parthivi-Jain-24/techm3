"""Canonical structured audit models (Phase 9).

``AuditEvent`` answers WHO / WHAT ACTION / WHICH RESOURCE / WHEN / WHICH
REQUEST / WITH WHAT OUTCOME for a single security- or governance-relevant
occurrence. It is a hard security boundary: fields are typed and validated so
free-form, potentially sensitive text cannot be smuggled in through the
"convenient" path -- the only open-ended field is ``metadata``, and every
event MUST pass through ``AuditService`` (never constructed ad hoc at a call
site) so ``metadata`` is always centrally sanitized before an event exists.

This module never imports from ``app.identity``, ``app.secrets``,
``app.encryption``, or ``app.ingestion`` -- the dependency direction is
one-way (those modules call into ``app.audit``, never the reverse), which is
also what keeps the audit sink independent of the secrets subsystem (no
recursive "audit needs a secret to log that a secret was accessed" loop).
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.audit.events.enums import ActorType, EventType, Outcome, Severity

# Stable, dotted, lowercase machine name: "domain.operation" or
# "domain.sub.operation" -- e.g. "authentication.succeeded",
# "ingestion.file.completed". No spaces, no uppercase, no free text.
_ACTION_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")

# Same shape requirement for resource_type ("api_endpoint", "secret_reference").
_RESOURCE_TYPE_RE = re.compile(r"^[a-z][a-z0-9_]*$")

MAX_ACTOR_ID_LENGTH = 200
MAX_RESOURCE_ID_LENGTH = 500


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Actor(BaseModel):
    """Who performed the action. Never a password/token/credential.

    ``actor_id`` is a stable internal identifier only (e.g. Principal.principal_id
    or "anonymous"/"system") -- never a full profile, email-unless-that-IS-the-
    stable-id, DOB, address, or document number. See docs/audit-logging.md
    "Actor privacy".
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    actor_id: str = Field(..., min_length=1, max_length=MAX_ACTOR_ID_LENGTH)
    actor_type: ActorType = ActorType.ANONYMOUS
    roles: tuple[str, ...] = Field(default_factory=tuple)


ANONYMOUS_ACTOR = Actor(actor_id="anonymous", actor_type=ActorType.ANONYMOUS)
SYSTEM_ACTOR = Actor(actor_id="system", actor_type=ActorType.SYSTEM)


class Resource(BaseModel):
    """Which resource was affected -- a safe category + a safe identifier.

    ``resource_id`` must NEVER be a full file path, raw record, secret value,
    credential, or key material -- only a safe filename, logical name, route
    template, or similar non-sensitive reference. See docs/audit-logging.md
    "Resource model".
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    resource_type: str = Field(..., min_length=1, max_length=100)
    resource_id: str | None = Field(default=None, max_length=MAX_RESOURCE_ID_LENGTH)

    @field_validator("resource_type")
    @classmethod
    def _validate_resource_type(cls, v: str) -> str:
        if not _RESOURCE_TYPE_RE.match(v):
            raise ValueError(
                "resource_type must be a lowercase snake_case identifier"
            )
        return v


class AuditEvent(BaseModel):
    """One canonical, structured, sanitized audit record.

    Always constructed via ``AuditService.emit`` -- never assembled as a bare
    dict anywhere else in the codebase (see docs/audit-logging.md "Audit
    service").
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = Field(default_factory=utcnow)
    event_type: EventType
    action: str
    outcome: Outcome
    severity: Severity = Severity.INFO
    request_id: str | None = None
    actor: Actor = ANONYMOUS_ACTOR
    resource: Resource | None = None
    source: str = "backend"
    duration_ms: float | None = Field(default=None, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("action")
    @classmethod
    def _validate_action(cls, v: str) -> str:
        if not _ACTION_RE.match(v):
            raise ValueError(
                "action must be a stable dotted machine name, e.g. "
                "'authentication.succeeded' (no spaces, no free text)"
            )
        return v

    @field_validator("timestamp")
    @classmethod
    def _timestamp_must_be_utc_aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware")
        return v.astimezone(timezone.utc)

    @field_validator("request_id")
    @classmethod
    def _request_id_bounded(cls, v: str | None) -> str | None:
        if v is not None and (not v or len(v) > 64):
            raise ValueError("request_id must be 1-64 characters")
        return v
