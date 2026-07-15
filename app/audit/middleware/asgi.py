"""Audit context middleware (Phase 9, PART E/F/U/V/W).

Deliberately a PLAIN ASGI middleware -- ``async def __call__(self, scope,
receive, send)`` -- rather than a ``starlette.middleware.base.BaseHTTPMiddleware``
subclass, for two reasons:

1. Body/streaming safety (PART F): a plain ASGI middleware never touches
   ``receive`` or the body of ``send`` messages at all -- it only inspects
   ``scope`` (method, path, headers) before the call and the
   ``http.response.start`` message's status code after. There is no
   iterate-the-body-then-reconstruct-the-response step (which is how
   ``BaseHTTPMiddleware`` works internally, and which can complicate
   streaming responses) -- request and response bodies pass through
   completely untouched.
2. Context propagation: the downstream app runs in the exact same
   coroutine/task as this middleware (a plain ``await self.app(...)``), so a
   ``contextvars`` value set here is reliably visible to every dependency,
   route handler, and internal service call for this request -- including
   code with no access to the ``Request`` object (encryption, secret
   resolution).

Never reads the request body. Never logs the raw query string or headers
(PART U) -- only method + a safe route template/path, and only the response
STATUS CODE, not its body (never Authorization/Cookie -- PART T).
"""

from __future__ import annotations

import time

from app.audit.events.actions import REQUEST_COMPLETED
from app.audit.events.enums import EventType, Outcome, Severity
from app.audit.events.models import Resource
from app.audit.events.resources import API_ENDPOINT
from app.audit.middleware.context import AuditContext, current_actor, reset_context, set_context
from app.audit.middleware.request_id import resolve_request_id
from app.audit.service import get_audit_service

_REQUEST_ID_HEADER = b"x-request-id"


def _incoming_request_id(scope) -> str | None:  # noqa: ANN001
    for key, value in scope.get("headers", []):
        if key.lower() == _REQUEST_ID_HEADER:
            try:
                return value.decode("latin-1")
            except UnicodeDecodeError:
                return None
    return None


def _safe_route_template(scope) -> str:  # noqa: ANN001
    """Safe path for the request -- NEVER the query string (PART U).

    In principle the matched route's TEMPLATE (e.g.
    ``/api/v1/ingestion/api/{source_id}/run`` with a placeholder rather than
    the real value) would be preferable to the concrete path. In practice,
    this FastAPI version wraps included sub-routers in an internal
    ``_IncludedRouter`` that does not eagerly flatten prefixes onto each
    route, so ``scope["route"].path`` at this middleware layer resolves to
    only the LEAF-relative path (e.g. ``"/live"`` instead of
    ``"/api/v1/health/live"``) -- less useful, and version-fragile to rely
    on. Rather than invent/reconstruct a template (PART E: "do not invent
    route names"), this uses ``scope["path"]``: the concrete, full request
    path, which ASGI guarantees never includes the query string. Any path
    PARAMETER values it reveals (e.g. a source_id) are not treated as
    sensitive elsewhere in this audit design either -- ``source_id`` is
    already used directly as an ``INGESTION_SOURCE`` resource_id (PART I) --
    so this is not a new leak. See docs/audit-logging.md "Middleware
    behavior" for this documented limitation.
    """
    return scope.get("path", "")


def _outcome_for_status(status: int | None) -> Outcome:
    if status is None:
        return Outcome.ERROR
    if status < 400:
        return Outcome.SUCCESS
    if status == 401 or status == 403:
        return Outcome.DENIED
    if status < 500:
        return Outcome.FAILURE
    return Outcome.ERROR


def _severity_for_status(status: int | None) -> Severity:
    if status is None or status >= 500:
        return Severity.ERROR
    if status in (401, 403) or status >= 400:
        return Severity.WARNING
    return Severity.INFO


class AuditContextMiddleware:
    """Establishes request correlation + audit context; emits the final
    ``request.completed`` audit event. See module docstring for why this is
    plain ASGI rather than ``BaseHTTPMiddleware``."""

    def __init__(self, app) -> None:  # noqa: ANN001
        self.app = app

    async def __call__(self, scope, receive, send) -> None:  # noqa: ANN001
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = resolve_request_id(_incoming_request_id(scope))
        ctx = AuditContext(request_id=request_id)
        token = set_context(ctx)

        status_holder: dict[str, int | None] = {"status": None}

        async def send_wrapper(message):  # noqa: ANN001
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", request_id.encode("ascii")))
                message = {**message, "headers": headers}
            await send(message)

        method = scope.get("method", "")
        start = time.monotonic()
        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration_ms = (time.monotonic() - start) * 1000
            status = status_holder["status"]
            path_template = _safe_route_template(scope)
            get_audit_service().emit(
                event_type=EventType.HTTP_REQUEST,
                action=REQUEST_COMPLETED,
                outcome=_outcome_for_status(status),
                severity=_severity_for_status(status),
                actor=current_actor(),
                resource=Resource(resource_type=API_ENDPOINT, resource_id=path_template),
                request_id=request_id,
                duration_ms=duration_ms,
                metadata={"method": method, "status_code": status},
            )
            reset_context(token)
