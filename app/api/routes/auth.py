"""OAuth2-compatible token endpoint.

Local password-based token flow for development / testing / hackathon demo only.
It is NOT a production SSO/authorization server — see docs/authentication-and-rbac.md
(production should use OAuth2 Authorization Code + PKCE / OIDC via an external IdP).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel

from app.audit.events.actions import AUTHENTICATION_FAILED, AUTHENTICATION_SUCCEEDED
from app.audit.events.enums import EventType, Outcome, Severity
from app.audit.middleware.context import actor_from_principal, set_actor
from app.audit.service import get_audit_service
from app.identity.authentication.dependencies import get_identity_provider
from app.identity.authentication.provider import IdentityProvider
from app.identity.authentication.tokens import create_access_token
from app.identity.errors import AuthConfigError

router = APIRouter()

# Authentication mechanism category for this endpoint's audit events — a
# fixed, non-user-controlled string (PART G: "authentication mechanism
# category"), never derived from request input.
_MECHANISM = "password"


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


@router.post("/token", response_model=TokenResponse)
def issue_token(
    form: OAuth2PasswordRequestForm = Depends(),
    provider: IdentityProvider = Depends(get_identity_provider),
) -> TokenResponse:
    # Generic failure: never reveal whether the username or the password was wrong.
    record = provider.authenticate(form.username, form.password)
    if record is None or not record.is_active:
        # No actor identity is known on failure -- deliberately NOT logging
        # the attempted username here preserves the same no-enumeration
        # guarantee this endpoint already gives callers (PART G).
        get_audit_service().emit(
            event_type=EventType.AUTHENTICATION,
            action=AUTHENTICATION_FAILED,
            outcome=Outcome.FAILURE,
            severity=Severity.WARNING,
            metadata={"mechanism": _MECHANISM},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        token = create_access_token(record.to_principal())
    except AuthConfigError:
        get_audit_service().emit(
            event_type=EventType.AUTHENTICATION,
            action=AUTHENTICATION_FAILED,
            outcome=Outcome.ERROR,
            severity=Severity.ERROR,
            metadata={"mechanism": _MECHANISM, "reason": "AUTHENTICATION_NOT_CONFIGURED"},
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is not configured",
        )
    principal = record.to_principal()
    set_actor(actor_from_principal(principal))
    get_audit_service().emit(
        event_type=EventType.AUTHENTICATION,
        action=AUTHENTICATION_SUCCEEDED,
        outcome=Outcome.SUCCESS,
        actor=actor_from_principal(principal),
        metadata={"mechanism": _MECHANISM},
    )
    return TokenResponse(access_token=token)
