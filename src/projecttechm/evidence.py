"""Thread-safe auto-incrementing evidence ID generator."""

from __future__ import annotations

import threading


class EvidenceIdGenerator:
    """Generates unique evidence IDs in the format EVD-NNN.

    Thread-safe via a lock so concurrent match pipelines won't collide.
    """

    def __init__(self, prefix: str = "EVD", start: int = 1) -> None:
        self._prefix = prefix
        self._counter = start
        self._lock = threading.Lock()

    def next_id(self) -> str:
        """Return the next unique evidence ID and advance the counter."""
        with self._lock:
            eid = f"{self._prefix}-{self._counter:03d}"
            self._counter += 1
            return eid

    def peek(self) -> int:
        """Return the current counter value without advancing."""
        with self._lock:
            return self._counter

    def reset(self, start: int = 1) -> None:
        """Reset the counter (useful for tests)."""
        with self._lock:
            self._counter = start


# Module-level default generator — import and use across the project.
evidence_id_gen = EvidenceIdGenerator()
