"""Local hash-chained JSON Lines audit sink (Phase 9, PART M/N/P + hash chain).

One event per line, UTF-8, append-only. Each written line additionally
carries ``previous_hash`` (the prior line's ``event_hash``, or the documented
genesis value for the first line) and ``event_hash`` (SHA-256 over the line's
own canonical content, excluding ``event_hash`` itself) -- see
``hashchain.py`` for exactly what this does and does not guarantee.

Concurrency: a per-process ``threading.Lock`` serializes writes so the
in-memory ``previous_hash`` pointer and the on-disk tail never diverge within
one process. This does NOT protect against multiple separate OS processes
appending to the same file concurrently -- out of scope for a local
hackathon demonstration sink (documented limitation).
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from app.audit.events.models import AuditEvent
from app.audit.storage.hashchain import GENESIS_HASH, canonical_json, compute_event_hash


class HashChainedJsonLinesAuditSink:
    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._lock = threading.Lock()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._previous_hash = self._read_last_hash()

    def _read_last_hash(self) -> str:
        if not self._path.exists():
            return GENESIS_HASH
        last_hash = GENESIS_HASH
        try:
            with self._path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    candidate = obj.get("event_hash")
                    if isinstance(candidate, str) and candidate:
                        last_hash = candidate
        except OSError:
            return GENESIS_HASH
        return last_hash

    def write(self, event: AuditEvent) -> None:
        payload = event.model_dump(mode="json")
        with self._lock:
            payload["previous_hash"] = self._previous_hash
            event_hash = compute_event_hash(payload)
            payload["event_hash"] = event_hash
            line = canonical_json(payload).decode("utf-8")
            # Any failure here (disk full, permissions, path unavailable) is
            # handled by AuditService's fail-safe policy -- this method
            # intentionally lets the exception propagate so the caller can
            # apply that policy once, centrally, rather than every sink
            # silently deciding its own behavior.
            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
                fh.flush()
                os.fsync(fh.fileno())
            self._previous_hash = event_hash
