"""Request-scoped audit context (Phase 9, PART E/X).

The middleware creates an anonymous context at request entry (before
authentication has run) and stores it in a ``contextvars.ContextVar``. Later,
once the existing Phase 4 authentication dependency has resolved a real
``Principal``, it enriches THIS SAME context object with a safe actor --
nothing re-parses a JWT or duplicates authentication here (PART X).

Using a pure-ASGI middleware (see ``asgi.py``) rather than
``BaseHTTPMiddleware`` means the downstream app runs in the exact same
coroutine/task as the middleware, so a contextvar set before
``await self.app(...)`` is reliably visible to every dependency, route
handler, and service call within that request -- including code (encryption,
secret resolution) that has no access to the ``Request`` object at all.
"""

from __future__ import annotations

import contextvars
from dataclasses import dataclass, field

from app.audit.events.models import ANONYMOUS_ACTOR, SYSTEM_ACTOR, Actor


@dataclass
class AuditContext:
    request_id: str
    actor: Actor = field(default_factory=lambda: ANONYMOUS_ACTOR)


_current_context: contextvars.ContextVar[AuditContext | None] = contextvars.ContextVar(
    "audit_context", default=None
)


def set_context(ctx: AuditContext) -> contextvars.Token:
    return _current_context.set(ctx)


def reset_context(token: contextvars.Token) -> None:
    _current_context.reset(token)


def get_context() -> AuditContext | None:
    return _current_context.get()


def current_request_id() -> str | None:
    ctx = get_context()
    return ctx.request_id if ctx is not None else None


def set_actor(actor: Actor) -> None:
    """Enrich the CURRENT request's audit context with a resolved actor.
    A no-op outside of an HTTP request (no context set) -- callers such as
    CLI jobs pass an explicit ``actor`` to ``AuditService.emit`` instead."""
    ctx = get_context()
    if ctx is not None:
        ctx.actor = actor


def current_actor() -> Actor:
    """The best-known actor for the current execution.

    - Inside an HTTP request before authentication: the anonymous actor.
    - Inside an HTTP request after ``set_actor`` enrichment: the real actor.
    - Outside any HTTP request (CLI jobs, startup code): the system actor --
      deliberately distinct from "anonymous", which specifically means "an
      HTTP request arrived with no valid credentials".
    """
    ctx = get_context()
    return ctx.actor if ctx is not None else SYSTEM_ACTOR


def actor_from_principal(principal) -> Actor:  # noqa: ANN001 - avoid import cycle
    """Build a safe ``Actor`` from a Phase 4 ``Principal``.

    Local import avoids a module-load-time cycle (``app.identity`` never
    imports ``app.audit``, but keeping the audit package importable in
    isolation -- e.g. for unit tests of the schema alone -- is worth the
    one-line indirection).
    """
    from app.audit.events.enums import ActorType
    from app.identity.authentication.models import PrincipalType

    mapped = (
        ActorType.SERVICE if principal.principal_type == PrincipalType.SERVICE else ActorType.USER
    )
    return Actor(
        actor_id=principal.principal_id,
        actor_type=mapped,
        roles=tuple(r.value for r in principal.roles),
    )
