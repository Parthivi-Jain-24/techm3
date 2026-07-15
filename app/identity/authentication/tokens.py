"""Short-lived signed JWT access tokens (HS256).

Uses PyJWT with an explicit algorithm allow-list. Minimal claims only: never
passwords, hashes, KYC/customer PII, or secrets. Authorization is NOT taken from
the token — the current principal is re-resolved from the identity provider on
every request, so token contents cannot elevate privileges.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import jwt

from app.core.config import settings
from app.identity.authentication.models import Principal
from app.identity.errors import AuthConfigError, InvalidTokenError

# Explicit allow-list. 'none' and asymmetric confusion are impossible here.
SUPPORTED_ALGORITHMS: frozenset[str] = frozenset({"HS256"})
_REQUIRED_CLAIMS = ("sub", "iat", "exp", "jti")


def _secret() -> str:
    secret = settings.jwt_secret_key
    if not secret:
        raise AuthConfigError("JWT signing secret is not configured")
    return secret


def _algorithm() -> str:
    alg = settings.jwt_algorithm
    if alg not in SUPPORTED_ALGORITHMS:
        raise AuthConfigError(f"unsupported JWT algorithm: {alg!r}")
    return alg


def create_access_token(
    principal: Principal,
    *,
    secret: str | None = None,
    algorithm: str | None = None,
    expires_minutes: int | None = None,
    now: datetime | None = None,
) -> str:
    """Create a signed access token for ``principal``. Claims are minimal:
    sub, principal_type, iat, exp, jti."""
    secret = secret or _secret()
    algorithm = algorithm or _algorithm()
    if algorithm not in SUPPORTED_ALGORITHMS:
        raise AuthConfigError(f"unsupported JWT algorithm: {algorithm!r}")
    minutes = expires_minutes if expires_minutes is not None else settings.access_token_expire_minutes
    issued = now or datetime.now(timezone.utc)
    claims = {
        "sub": principal.principal_id,
        "principal_type": principal.principal_type.value,
        "iat": issued,
        "exp": issued + timedelta(minutes=minutes),
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(claims, secret, algorithm=algorithm)


def decode_access_token(
    token: str,
    *,
    secret: str | None = None,
    algorithms: list[str] | None = None,
) -> dict:
    """Validate a token and return its claims, or raise ``InvalidTokenError``.

    Enforces signature, expiry, and presence of required claims, and only
    accepts algorithms from the allow-list. Failure detail is never leaked.
    """
    secret = secret or _secret()
    algorithms = algorithms or [_algorithm()]
    if any(a not in SUPPORTED_ALGORITHMS for a in algorithms):
        raise AuthConfigError("unsupported JWT algorithm requested")
    try:
        return jwt.decode(
            token,
            secret,
            algorithms=list(algorithms),
            options={"require": list(_REQUIRED_CLAIMS)},
        )
    except jwt.PyJWTError as exc:  # expired, bad signature, malformed, missing claim
        raise InvalidTokenError("token validation failed") from exc
