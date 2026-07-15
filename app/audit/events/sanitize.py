"""Centralized audit-metadata sanitization boundary (Phase 9, PART R/S).

Every ``AuditEvent.metadata`` dict passes through :func:`sanitize_metadata`
inside ``AuditService.emit`` -- call sites never write straight to a sink.
This is deliberate defense in depth: even if a call site accidentally passes
something sensitive, this boundary is the last line of defense before it
becomes a persisted, structured record.

Two independent controls:

1. Key-name redaction -- a deliberate, explicit substring list (never the
   bare word "key", which would blindly nuke legitimate non-secret fields
   like ``key_id`` / ``secret_id`` / ``secret_reference``).
2. Structural bounds -- depth, string length, collection size -- so a caller
   can never accidentally (or maliciously) place an entire KYC dataset, a
   deeply nested object graph, or a giant blob into ``metadata``.
"""

from __future__ import annotations

from typing import Any

REDACTED = "[REDACTED]"

# Deliberate, explicit substrings -- each chosen so it does NOT accidentally
# match legitimate non-secret metadata keys such as "key_id", "secret_id",
# "secret_reference", "secret_name", "source_id", "artifact_id". Matching is
# case-insensitive against the FULL key name (not fuzzy substring-of-word),
# i.e. "password" catches "password"/"user_password"/"db_password" but the
# bare substring "key" is intentionally never used as a trigger on its own.
_SENSITIVE_KEY_SUBSTRINGS: tuple[str, ...] = (
    "password",
    "passwd",
    "secret_value",
    "secret_key",
    "client_secret",
    "token",
    "authorization",
    "api_key",
    "apikey",
    "encryption_key",
    "private_key",
    "vault_token",
    "credential",
    "cookie",
    "session_id",
    "refresh_token",
    "access_token",
    "signing_key",
    "hmac_key",
    "passphrase",
)

# Explicit allow-list: these exact key names are legitimate non-secret
# identifiers even though they contain substrings that might look sensitive
# at a glance (e.g. "secret" appears in "secret_id"). Checked BEFORE the
# substring scan, so an allow-listed key is never redacted.
_ALLOWED_EXACT_KEYS: frozenset[str] = frozenset(
    {
        "key_id",
        "secret_id",
        "secret_reference",
        "secret_name",
        "logical_secret_name",
        "resource_id",
        "resource_type",
        "source_id",
        "source_type",
        "artifact_id",
        "artifact_type",
        "provider_type",
        "permission",
        "required_permission",
        "algorithm",
        "mechanism",
    }
)

# --- Structural bounds (PART S) -------------------------------------------- #
MAX_METADATA_DEPTH = 4
MAX_STRING_LENGTH = 512
MAX_COLLECTION_SIZE = 20
MAX_DICT_KEYS = 30

_TRUNCATED_SUFFIX = "...[TRUNCATED]"
_DEPTH_LIMIT_MARKER = "[DEPTH_LIMIT_EXCEEDED]"
_COLLECTION_LIMIT_MARKER = "[COLLECTION_TRUNCATED]"


def _is_sensitive_key(key: str) -> bool:
    lowered = key.strip().lower()
    if lowered in _ALLOWED_EXACT_KEYS:
        return False
    return any(pattern in lowered for pattern in _SENSITIVE_KEY_SUBSTRINGS)


def _bound_string(value: str) -> str:
    if len(value) <= MAX_STRING_LENGTH:
        return value
    return value[:MAX_STRING_LENGTH] + _TRUNCATED_SUFFIX


def _sanitize_value(value: Any, depth: int) -> Any:
    if depth > MAX_METADATA_DEPTH:
        return _DEPTH_LIMIT_MARKER

    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        return _bound_string(value)
    if isinstance(value, dict):
        return _sanitize_dict(value, depth)
    if isinstance(value, (list, tuple, set, frozenset)):
        items = list(value)[:MAX_COLLECTION_SIZE]
        sanitized = [_sanitize_value(item, depth + 1) for item in items]
        if len(value) > MAX_COLLECTION_SIZE:
            sanitized.append(_COLLECTION_LIMIT_MARKER)
        return sanitized
    # Anything else (exceptions, custom objects, bytes, ...) is NOT trusted
    # to be safely JSON-serializable or free of sensitive content by
    # accident -- fall back to a bounded, generic type marker rather than
    # str()-ing an arbitrary object (which could embed repr() of secrets).
    return f"[UNSERIALIZABLE:{type(value).__name__}]"


def _sanitize_dict(data: dict, depth: int) -> dict:
    if depth > MAX_METADATA_DEPTH:
        return {"_": _DEPTH_LIMIT_MARKER}
    result: dict[str, Any] = {}
    for i, (key, value) in enumerate(data.items()):
        if i >= MAX_DICT_KEYS:
            result["_truncated"] = _COLLECTION_LIMIT_MARKER
            break
        safe_key = _bound_string(str(key))
        if _is_sensitive_key(str(key)):
            result[safe_key] = REDACTED
        else:
            result[safe_key] = _sanitize_value(value, depth + 1)
    return result


def sanitize_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    """Recursively redact sensitive keys and bound size/depth/length.

    Never raises -- any metadata that cannot be handled degrades to a safe
    placeholder rather than propagating an exception into the caller's
    primary operation (fail-safe, see docs/audit-logging.md "Sink failure
    policy" for the analogous sink-level policy).
    """
    if not metadata:
        return {}
    try:
        return _sanitize_dict(dict(metadata), depth=0)
    except Exception:  # noqa: BLE001 - sanitization must never break the caller
        return {"_sanitization_error": True}
