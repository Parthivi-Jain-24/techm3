"""Run the KYC ingestion pipeline and print a concise, PII-safe summary.

Usage (from backend/):
    python -m app.ingestion.jobs.run_kyc_ingestion [FILENAME] [--write-jsonl]

FILENAME must live inside the approved KYC directory. ``--write-jsonl`` writes a
normalized development artifact under data/processed/ (git-ignored). Raw
customer records are never printed.
"""

from __future__ import annotations

import argparse

from app.core.config import settings
from app.ingestion.connectors.kyc_file_connector import discover_kyc_files
from app.ingestion.pipelines.kyc_ingestion_pipeline import (
    default_processed_path,
    ingest_kyc_file,
    write_processed_jsonl,
)


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
    parser = argparse.ArgumentParser(description="Run KYC ingestion (PII-safe summary).")
    parser.add_argument("filename", nargs="?", help="File name inside approved KYC dir.")
    parser.add_argument(
        "--write-jsonl",
        action="store_true",
        help="Write normalized entities to data/processed/ (git-ignored).",
    )
    args = parser.parse_args(argv)

    filename = _pick_filename(args.filename)
    result = ingest_kyc_file(filename)
    r = result.report

    print("=== KYC ingestion summary ===")
    print(f"source_file            : {r.source_file}")
    print(f"total_rows             : {r.total_rows}")
    print(f"valid_rows             : {r.valid_rows}")
    print(f"invalid_rows           : {r.invalid_rows}")
    print(f"duplicate_client_ids   : {r.duplicate_client_ids}")
    print(f"missing_required_fields: {r.missing_required_field_counts or 'none'}")
    print(f"validation_issue_counts: {r.validation_issue_counts or 'none'}")
    print(f"additional_source_cols : {r.additional_source_columns or 'none'}")
    print(f"missing_expected_cols  : {r.missing_expected_source_columns or 'none'}")
    print(f"entities_produced      : {len(result.entities)}")

    if args.write_jsonl:
        out = write_processed_jsonl(result, default_processed_path(r.source_file))
        print(f"processed_artifact     : {out}")


if __name__ == "__main__":
    main()
