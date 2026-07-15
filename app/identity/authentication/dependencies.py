"""FastAPI authentication dependencies.

``get_current_principal`` extracts the bearer token, validates the JWT, and
re-resolves the CURRENT principal from the trusted identity provider (so token
contents can never elevate privileges or bypass an is_active check).
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from app.audit.events.actions import AUTHENTICATION_FAILED
from app.audit.events.enums import EventType, Outcome, Severity
from app.audit.middleware.context import actor_from_principal, set_actor
from app.audit.service import get_audit_service
from app.core.config import settings
from app.identity.authentication.models import Principal
from app.identity.authentication.provider import (
    IdentityProvider,
    build_dev_provider_from_config,
)
from app.identity.authentication.tokens import decode_access_token
from app.identity.errors import AuthConfigError, InvalidTokenError

# auto_error=False so we can return a consistent 401 with WWW-Authenticate.
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.api_v1_prefix}/auth/token".lstrip("/"),
    auto_error=False,
)

_CREDENTIALS_EXCEPTION = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)

# Module-level dev provider built once from configuration. Tests override the
# ``get_identity_provider`` dependency rather than mutating this.
_provider = build_dev_provider_from_config(settings.dev_auth_users)


def get_identity_provider() -> IdentityProvider:
    return _provider


def _audit_bearer_rejected(reason: str, *, outcome: Outcome = Outcome.FAILURE) -> None:
    # No token presented at all (anonymous request to a protected endpoint)
    # is intentionally NOT audited here -- that is not a rejected credential,
    # just an unauthenticated request, and already shows up as a 401 in the
    # request.completed event. This helper is only called once a credential
    # WAS presented and rejected.
    get_audit_service().emit(
        event_type=EventType.AUTHENTICATION,
        action=AUTHENTICATION_FAILED,
        outcome=outcome,
        severity=Severity.WARNING,
        metadata={"mechanism": "bearer_token", "reason": reason},
    )


def get_current_principal(
    token: str | None = Depends(oauth2_scheme),
    provider: IdentityProvider = Depends(get_identity_provider),
) -> Principal:
    if not token:
        raise _CREDENTIALS_EXCEPTION
    try:
        claims = decode_access_token(token)
    except AuthConfigError:
        _audit_bearer_rejected("AUTHENTICATION_NOT_CONFIGURED", outcome=Outcome.ERROR)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is not configured",
        )
    except InvalidTokenError:
        _audit_bearer_rejected("INVALID_TOKEN")
        raise _CREDENTIALS_EXCEPTION

    record = provider.get_by_id(claims["sub"])
    if record is None or not record.is_active:  # unknown or deactivated -> deny
        _audit_bearer_rejected("UNKNOWN_OR_INACTIVE_PRINCIPAL")
        raise _CREDENTIALS_EXCEPTION

    principal = record.to_principal()
    # Enrich THIS request's audit context so later authorization/domain
    # events (and the final request.completed event) attribute correctly --
    # not a separate "authentication succeeded" event on every single
    # protected call (that would fire once per request and duplicate the
    # per-login event already emitted at /auth/token; see
    # docs/audit-logging.md "Authentication events").
    set_actor(actor_from_principal(principal))
    return principal
