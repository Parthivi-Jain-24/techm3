"""Safe, read-only inspection of a KYC dataset file.

Prints ONLY aggregate, PII-safe information: columns, row count, null counts,
duplicate client_id count, and low-cardinality category summaries. It never
prints raw customer names and never mutates the source file.

Usage (from backend/):
    python -m app.ingestion.jobs.inspect_kyc_dataset [FILENAME]

FILENAME must live inside the approved KYC directory (settings.kyc_raw_dir).
If omitted, the single discovered file is used (or the available files listed).
"""

from __future__ import annotations

import argparse
import collections

from app.core.config import settings
from app.ingestion.connectors.kyc_file_connector import (
    discover_kyc_files,
    read_csv_rows,
)
from app.ingestion.mapping import BOOLEAN_FIELDS, REQUIRED_SOURCE_COLUMNS
from app.ingestion.reports import mask_identifier
from app.ingestion.validators.file_validator import validate_kyc_file

# Non-PII columns whose distinct values are safe to summarize.
_SAFE_CATEGORICAL = ("client_type", "sector_risk", "sector", *BOOLEAN_FIELDS)
# Columns treated as PII — never printed, only counted.
_PII_COLUMNS = frozenset({"client_name"})


def _pick_filename(explicit: str | None) -> str:
    if explicit:
        return explicit
    found = discover_kyc_files()
    if len(found) == 1:
        return found[0].name
    if not found:
        raise SystemExit(
            f"No KYC files found in approved dir: {settings.kyc_raw_path}\n"
            f"Place the KYC CSV there (see docs/kyc-ingestion.md)."
        )
    names = ", ".join(p.name for p in found)
    raise SystemExit(f"Multiple KYC files found; specify one of: {names}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Inspect a KYC dataset safely.")
    parser.add_argument("filename", nargs="?", help="File name inside approved KYC dir.")
    args = parser.parse_args(argv)

    filename = _pick_filename(args.filename)
    path = validate_kyc_file(filename)
    header, rows = read_csv_rows(path)

    print(f"file            : {path.name}")
    print(f"format          : CSV (utf-8)")
    print(f"columns ({len(header)})    : {header}")
    print(f"data rows       : {len(rows)}")

    missing_required = [c for c in REQUIRED_SOURCE_COLUMNS if c not in header]
    print(f"missing required: {missing_required or 'none'}")

    # Null counts per column (blank after strip).
    nulls = {
        c: sum(1 for r in rows if not (r.get(c, "") or "").strip()) for c in header
    }
    print(f"null counts     : {nulls}")

    # Duplicate client_id (masked, count only).
    ids = [(r.get("client_id", "") or "").strip() for r in rows]
    dup = {cid for cid, n in collections.Counter(ids).items() if cid and n > 1}
    print(f"unique client_id: {len(set(i for i in ids if i))}")
    print(f"dup client_id   : {len(dup)}  e.g. {[mask_identifier(c) for c in list(dup)[:3]]}")

    # PII columns: report only presence + length stats, never values.
    for c in header:
        if c in _PII_COLUMNS:
            lens = [len((r.get(c, '') or '').strip()) for r in rows]
            mn = min(lens) if lens else 0
            mx = max(lens) if lens else 0
            print(f"[PII] {c}: len {mn}-{mx} (values not shown)")

    # Safe categorical summaries (bounded cardinality).
    for c in _SAFE_CATEGORICAL:
        if c not in header:
            continue
        counter = collections.Counter((r.get(c, "") or "").strip() for r in rows)
        if len(counter) <= 25:
            print(f"{c:>18}: {dict(counter.most_common())}")
        else:
            print(f"{c:>18}: cardinality={len(counter)} (top5 {dict(counter.most_common(5))})")


if __name__ == "__main__":
    main()
