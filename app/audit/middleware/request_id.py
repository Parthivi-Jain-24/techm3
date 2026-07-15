"""Request-ID generation and strict validation (Phase 9, PART D).

Accepts an incoming ``X-Request-ID`` only if it is a well-formed UUID within
a bounded length -- anything else (missing, malformed, overlong, containing
control/newline characters) is replaced with a freshly generated UUID4.
There is no path by which a caller can inject arbitrary or unbounded text
into a value that later gets embedded in structured audit output.
"""

from __future__ import annotations

import re
import uuid

MAX_REQUEST_ID_LENGTH = 64

_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def generate_request_id() -> str:
    return str(uuid.uuid4())


def resolve_request_id(incoming: str | None) -> str:
    """Return a valid request ID: the caller's UUID if well-formed, else a
    newly generated one. Never echoes back non-UUID input."""
    if incoming:
        candidate = incoming.strip()
        if 0 < len(candidate) <= MAX_REQUEST_ID_LENGTH and _UUID_RE.match(candidate):
            return candidate
    return generate_request_id()
