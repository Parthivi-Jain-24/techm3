"""Offline verification for a hash-chained audit JSONL file (Phase 9).

Usage (from ``backend/``):

    python -m app.audit.verify <path-to-audit.jsonl>

Reports whether the hash chain is valid, and if not, the line number of the
first detected failure and a safe reason category. Never prints event
content (actor/resource/metadata) -- only line numbers and structural
failure categories -- so running this tool against a real audit file cannot
itself become a leakage path.

This tool does NOT require Vault, a database, network access, or any secret
-- verification is pure local hashing (PART: "Verification does not require
secret keys").
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from app.audit.storage.hashchain import GENESIS_HASH, canonical_json


@dataclass(frozen=True)
class VerificationResult:
    valid: bool
    lines_checked: int
    failed_line: int | None = None
    reason: str | None = None


def verify_chain(path: Path) -> VerificationResult:
    previous_hash = GENESIS_HASH
    lines_checked = 0

    with Path(path).open("r", encoding="utf-8") as fh:
        for line_number, raw_line in enumerate(fh, start=1):
            line = raw_line.strip()
            if not line:
                continue

            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                return VerificationResult(
                    valid=False,
                    lines_checked=lines_checked,
                    failed_line=line_number,
                    reason="malformed JSON line",
                )

            if not isinstance(obj, dict) or "event_hash" not in obj or "previous_hash" not in obj:
                return VerificationResult(
                    valid=False,
                    lines_checked=lines_checked,
                    failed_line=line_number,
                    reason="missing hash-chain fields",
                )

            claimed_hash = obj["event_hash"]
            claimed_previous = obj["previous_hash"]

            if claimed_previous != previous_hash:
                return VerificationResult(
                    valid=False,
                    lines_checked=lines_checked,
                    failed_line=line_number,
                    reason="broken previous_hash link (reordered, deleted, or inserted line)",
                )

            payload_without_hash = {k: v for k, v in obj.items() if k != "event_hash"}
            import hashlib

            recomputed = hashlib.sha256(canonical_json(payload_without_hash)).hexdigest()

            if recomputed != claimed_hash:
                return VerificationResult(
                    valid=False,
                    lines_checked=lines_checked,
                    failed_line=line_number,
                    reason="event hash mismatch (content modified)",
                )

            previous_hash = claimed_hash
            lines_checked += 1

    return VerificationResult(valid=True, lines_checked=lines_checked)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify a hash-chained audit JSONL file's integrity (Phase 9)."
    )
    parser.add_argument("path", help="Path to the audit .jsonl file to verify.")
    args = parser.parse_args(argv)

    file_path = Path(args.path)
    if not file_path.exists():
        print(f"ERROR: audit file not found: {file_path}")
        return 2

    result = verify_chain(file_path)
    if result.valid:
        print(f"VALID chain: {result.lines_checked} event(s) verified, no tampering detected.")
        return 0

    print(
        f"INVALID chain: failure detected at line {result.failed_line} "
        f"({result.lines_checked} prior event(s) verified OK). Reason: {result.reason}"
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
