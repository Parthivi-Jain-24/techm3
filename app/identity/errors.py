"""Identity/auth errors. Kept generic so nothing internal leaks to clients."""

from __future__ import annotations


class IdentityError(Exception):
    """Base class for identity/auth errors."""


class AuthConfigError(IdentityError):
    """Authentication is misconfigured (e.g. missing signing secret).

    Surfaced to clients as a generic 503 — never with configuration details.
    """


class InvalidTokenError(IdentityError):
    """A token failed validation (bad signature, expired, malformed, missing
    claim, unsupported algorithm). Deliberately carries no detail so callers
    cannot distinguish the failure cause."""
