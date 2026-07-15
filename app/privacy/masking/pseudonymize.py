"""Keyed pseudonymization for log-safe / external identifiers.

Uses HMAC-SHA256 with a secret key rather than a plain hash, because identifier
value spaces (e.g. numeric client_ids) can be small and guessable — a plain
unsalted hash would be reversible by brute force.

Key resolution order:
  1. explicit ``key`` argument (tests inject a key here);
  2. ``settings.pseudonymization_key`` from the environment;
  3. a clearly-insecure development fallback (below) so local runs/tests work.

The DEV fallback is NOT a secret and MUST NOT be relied on outside local dev —
set ``PSEUDONYMIZATION_KEY`` in the environment for any real deployment. The key
is never logged and never appears in output.
"""

from __future__ import annotations

import hashlib
import hmac

from app.core.config import settings

# Public, deliberately-insecure placeholder. Not a secret; documented as such.
_DEV_FALLBACK_KEY = "insecure-dev-pseudonymization-key-not-for-production"

_PREFIX = "anon_"
_DIGEST_CHARS = 16


def _resolve_key(key: str | None) -> str:
    if key:
        return key
    if settings.pseudonymization_key:
        return settings.pseudonymization_key
    return _DEV_FALLBACK_KEY


def pseudonymize(value: str | None, key: str | None = None) -> str:
    """Return a stable, non-reversible pseudonym for ``value``.

    Deterministic: same ``value`` + same key -> same pseudonym. The raw value
    and the key never appear in the output. Empty/None -> "".
    """
    text = "" if value is None else str(value)
    if text == "":
        return ""
    resolved = _resolve_key(key)
    digest = hmac.new(resolved.encode("utf-8"), text.encode("utf-8"), hashlib.sha256)
    return _PREFIX + digest.hexdigest()[:_DIGEST_CHARS]
