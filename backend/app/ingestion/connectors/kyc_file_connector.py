"""KYC file connector: approved-path resolution, discovery, and safe reading.

Security posture (see docs/kyc-ingestion.md):
  * Files are only ever resolved INSIDE the approved KYC directory. Absolute
    paths, ``..`` traversal, and symlink escapes are rejected.
  * Reading is CSV (stdlib ``csv``) or XLSX (``openpyxl``). Spreadsheet
    formulas are NEVER evaluated: openpyxl is not a calculation engine, and
    the workbook is opened ``data_only=True`` (cached values, not formula
    text) in streaming ``read_only=True`` mode. Cell values are read as
    strings; no spreadsheet output is ever written, so formula/CSV-injection
    on export is not applicable.
  * No raw customer data is logged.
"""

from __future__ import annotations

import csv
from pathlib import Path

from app.core.config import settings
from app.ingestion.errors import CorruptFileError, KycPathError, MissingFileError

# Formats actually supported. CSV (stdlib) and XLSX (openpyxl, read-only).
SUPPORTED_EXTENSIONS: frozenset[str] = frozenset({".csv", ".xlsx"})

# Defense-in-depth against a decompression / row "bomb": a small compressed
# .xlsx can expand to an enormous number of rows. The on-disk size limit
# (file_validator) bounds the COMPRESSED bytes; this bounds the DECOMPRESSED
# row count regardless. Generous vs. any realistic KYC dataset.
MAX_XLSX_ROWS: int = 1_000_000


def _approved_root(approved_dir: Path | str | None) -> Path:
    root = Path(approved_dir) if approved_dir is not None else settings.kyc_raw_path
    return root.resolve()


def resolve_kyc_path(filename: str, approved_dir: Path | str | None = None) -> Path:
    """Resolve ``filename`` to an absolute path INSIDE the approved KYC dir.

    ``filename`` is expected to be a bare name (e.g. ``clients.csv``). Any input
    that escapes the approved directory — absolute paths, ``..`` traversal, or
    symlinks pointing outside — is rejected with ``KycPathError``.
    """
    if not filename or not filename.strip():
        raise KycPathError("empty filename")

    root = _approved_root(approved_dir)

    # Reject obviously unsafe inputs early for clear errors.
    raw = filename.strip()
    if Path(raw).is_absolute() or raw.startswith(("/", "\\")):
        raise KycPathError("absolute paths are not allowed")
    if ".." in Path(raw).parts:
        raise KycPathError("path traversal ('..') is not allowed")

    # The real guard: resolve (follows symlinks) and require containment.
    candidate = (root / raw).resolve()
    if candidate != root and root not in candidate.parents:
        raise KycPathError("resolved path escapes the approved KYC directory")

    return candidate


def discover_kyc_files(approved_dir: Path | str | None = None) -> list[Path]:
    """List supported KYC files directly inside the approved directory."""
    root = _approved_root(approved_dir)
    if not root.is_dir():
        return []
    return sorted(
        p
        for p in root.iterdir()
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS
    )


def read_csv_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    """Read a CSV as (header, rows) with ALL values as strings.

    Strings-only avoids implicit dtype inference (important for booleans and
    numeric-looking client_ids). ``utf-8-sig`` transparently strips a BOM.
    Raises ``MissingFileError`` if the file is absent.
    """
    if not path.is_file():
        raise MissingFileError(f"not a file: {path.name}")

    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        header = list(reader.fieldnames or [])
        rows: list[dict[str, str]] = []
        for record in reader:
            # Normalize None (short rows) to empty string; keep everything str.
            rows.append({k: ("" if v is None else str(v)) for k, v in record.items()})
    return header, rows


def _cell_to_str(value: object) -> str:
    """Coerce an XLSX cell value to a string, matching CSV all-strings semantics.

    ``None`` (blank cell, or a formula cell with no cached value) becomes an
    empty string — never the literal ``"None"``. Booleans/numbers/datetimes are
    stringified so the shared normalizer treats them exactly like CSV text.
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        # str(True) -> "True"; keep it consistent with how CSV booleans arrive.
        return "True" if value else "False"
    return str(value)


def read_xlsx_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    """Read the FIRST worksheet of an XLSX as (header, rows), all values str.

    Security: opened ``read_only=True`` (streaming, memory-bounded) and
    ``data_only=True`` (cached cell values, never formula text — and openpyxl
    never *evaluates* formulas). Only the first/active sheet is read (documented
    behavior; additional sheets are ignored, never silently merged). A corrupt
    or non-XLSX file raises ``CorruptFileError`` without leaking parser
    internals. Row count is capped (:data:`MAX_XLSX_ROWS`) as decompression-bomb
    defense-in-depth. Raises ``MissingFileError`` if the file is absent.
    """
    if not path.is_file():
        raise MissingFileError(f"not a file: {path.name}")

    try:
        import openpyxl
    except ImportError as exc:  # pragma: no cover - dependency is declared
        raise CorruptFileError("XLSX support is unavailable") from exc

    try:
        workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    except Exception as exc:  # noqa: BLE001 - corrupt/not-a-zip/etc; never leak internals
        raise CorruptFileError(f"could not parse XLSX file: {path.name}") from exc

    try:
        worksheet = workbook.worksheets[0] if workbook.worksheets else None
        if worksheet is None:
            return [], []

        row_iter = worksheet.iter_rows(values_only=True)
        try:
            header_row = next(row_iter)
        except StopIteration:
            return [], []  # empty sheet

        header = [_cell_to_str(c).strip() for c in header_row]
        # Drop trailing all-empty header columns (openpyxl can over-report width).
        while header and header[-1] == "":
            header.pop()
        if not header:
            return [], []

        rows: list[dict[str, str]] = []
        for i, raw in enumerate(row_iter):
            if i >= MAX_XLSX_ROWS:
                raise CorruptFileError(
                    f"XLSX exceeds maximum supported row count ({MAX_XLSX_ROWS})"
                )
            # Skip fully-empty rows (openpyxl yields trailing blank rows).
            if raw is None or all(c is None for c in raw):
                continue
            record = {
                header[j]: _cell_to_str(raw[j]) if j < len(raw) else ""
                for j in range(len(header))
            }
            rows.append(record)
        return header, rows
    finally:
        workbook.close()


def read_kyc_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    """Dispatch to the reader for ``path``'s (already-validated) extension.

    ``validate_kyc_file`` has already confirmed the extension is supported and
    the path is safe; this only routes to the concrete reader.
    """
    suffix = path.suffix.lower()
    if suffix == ".xlsx":
        return read_xlsx_rows(path)
    return read_csv_rows(path)
