"""SHA-256 hash-chain primitives shared by the writer (``jsonl.py``) and the
offline verifier (``app.audit.verify``) -- kept in one place so write-time and
verify-time canonicalization can never drift apart.

Tamper-evidence scope (see docs/audit-logging.md "Tamper-evidence
limitations"): this chain makes it detectable if an existing line is
modified, reordered, or removed from the middle of the file. It does NOT:

- prevent someone with filesystem access from deleting the entire file or
  truncating trailing lines and re-chaining a fabricated tail from that point,
- provide non-repudiation (no signing key / HMAC secret is used),
- replace centralized, access-controlled, append-only production storage.

No custom cryptography is implemented -- only the standard library's
``hashlib.sha256`` over a deterministic JSON encoding.
"""

from __future__ import annotations

import hashlib
import json

# Documented genesis value for the first event in a chain (PART on hash
# chaining, requirement 1). 64 hex zero characters -- same length as a real
# SHA-256 digest, but structurally impossible to collide with a real hash of
# non-trivial content, and immediately recognizable as "no prior event".
GENESIS_HASH = "0" * 64


def canonical_json(payload: dict) -> bytes:
    """Deterministic JSON encoding: sorted keys, no extra whitespace.

    Used identically for hashing at write time and at verification time.
    """
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(
        "utf-8"
    )


def compute_event_hash(payload_without_hash: dict) -> str:
    """SHA-256 of the canonical event content (including ``previous_hash``)
    -- ``event_hash`` itself must NOT be a key in ``payload_without_hash``."""
    if "event_hash" in payload_without_hash:
        raise ValueError("payload_without_hash must not already contain event_hash")
    return hashlib.sha256(canonical_json(payload_without_hash)).hexdigest()
