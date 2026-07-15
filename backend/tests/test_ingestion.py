"""Phase 2 tests: secure KYC ingestion and normalization (CSV channel).

Fully self-contained: synthetic fixtures written to temporary directories. No
network, database, or dependency on the real challenge dataset.

XLSX ingestion (added in Phase 10) is covered separately in
tests/test_xlsx_ingestion.py — it shares this module's validation,
normalization, dedup, and audit pipeline via the channel-agnostic
``read_kyc_rows`` dispatch + ``normalize_batch``.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from app.ingestion.errors import (
    EmptyFileError,
    FileTooLargeError,
    KycPathError,
    SourceSchemaError,
    UnsupportedFileTypeError,
)
from app.ingestion.mapping import normalize_bool
from app.ingestion.pipelines.kyc_ingestion_pipeline import ingest_kyc_file
from app.ingestion.reports import IssueCode, ValidationIssue
from app.schemas.kyc import NormalizedKYCEntity, SectorRiskLevel

SOURCE_COLUMNS = [
    "client_id",
    "client_name",
    "client_type",
    "sector",
    "sector_risk",
    "country",
    "pep_flag",
    "sanctions_flag",
    "fatf_country_flag",
]


def _row(**overrides) -> dict[str, str]:
    row = dict(
        client_id="1",
        client_name="Acme Corp",
        client_type="Corporate",
        sector="Technology",
        sector_risk="High",
        country="in",
        pep_flag="0",
        sanctions_flag="1",
        fatf_country_flag="0",
    )
    row.update(overrides)
    return row


def _write_csv(directory: Path, name: str, rows: list[dict[str, str]],
               header: list[str] | None = None) -> None:
    header = header or SOURCE_COLUMNS
    with (directory / name).open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=header)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)


def _ingest(directory: Path, name: str, **kw):
    return ingest_kyc_file(name, approved_dir=directory, **kw)


# --------------------------------------------------------------------------- #
# 1. Valid CSV ingestion / 18. valid rows produce entities
# --------------------------------------------------------------------------- #
def test_valid_csv_ingestion_produces_entities(tmp_path: Path) -> None:
    _write_csv(tmp_path, "kyc.csv", [_row(client_id="1"), _row(client_id="2")])
    result = _ingest(tmp_path, "kyc.csv")
    assert result.report.total_rows == 2
    assert result.report.valid_rows == 2
    assert result.report.invalid_rows == 0
    assert all(isinstance(e, NormalizedKYCEntity) for e in result.entities)
    assert result.entities[0].country == "IN"  # normalized upper-case
    assert result.entities[0].sector_risk == SectorRiskLevel.HIGH


# --------------------------------------------------------------------------- #
# 3. Unsupported file type rejection
# --------------------------------------------------------------------------- #
def test_unsupported_file_type_rejected(tmp_path: Path) -> None:
    (tmp_path / "data.txt").write_text("client_id\n1\n", encoding="utf-8")
    with pytest.raises(UnsupportedFileTypeError):
        _ingest(tmp_path, "data.txt")


# --------------------------------------------------------------------------- #
# 4. Path traversal rejection / 5. outside approved dir rejection
# --------------------------------------------------------------------------- #
def test_path_traversal_rejected(tmp_path: Path) -> None:
    approved = tmp_path / "approved"
    approved.mkdir()
    with pytest.raises(KycPathError):
        _ingest(approved, "../evil.csv")


def test_absolute_path_rejected(tmp_path: Path) -> None:
    approved = tmp_path / "approved"
    approved.mkdir()
    outside = tmp_path / "outside.csv"
    outside.write_text("x", encoding="utf-8")
    with pytest.raises(KycPathError):
        _ingest(approved, str(outside.resolve()))


# --------------------------------------------------------------------------- #
# 6. Empty file rejection
# --------------------------------------------------------------------------- #
def test_empty_file_rejected(tmp_path: Path) -> None:
    (tmp_path / "empty.csv").write_text("", encoding="utf-8")
    with pytest.raises(EmptyFileError):
        _ingest(tmp_path, "empty.csv")


# --------------------------------------------------------------------------- #
# 7. Oversized file rejection (small test-configured limit)
# --------------------------------------------------------------------------- #
def test_oversized_file_rejected(tmp_path: Path) -> None:
    _write_csv(tmp_path, "big.csv", [_row(client_id=str(i)) for i in range(50)])
    with pytest.raises(FileTooLargeError):
        _ingest(tmp_path, "big.csv", max_size_mb=0.0005)  # ~524 bytes


# --------------------------------------------------------------------------- #
# 8. Missing required source column handling
# --------------------------------------------------------------------------- #
def test_missing_required_source_column_raises(tmp_path: Path) -> None:
    header = [c for c in SOURCE_COLUMNS if c != "client_id"]
    _write_csv(tmp_path, "noid.csv", [{k: "x" for k in header}], header=header)
    with pytest.raises(SourceSchemaError):
        _ingest(tmp_path, "noid.csv")


# --------------------------------------------------------------------------- #
# 9/10. Missing & blank client_id / 11. blank client_name
# --------------------------------------------------------------------------- #
def test_blank_client_id_is_invalid_not_emitted(tmp_path: Path) -> None:
    _write_csv(tmp_path, "k.csv", [_row(client_id="   ")])
    result = _ingest(tmp_path, "k.csv")
    assert result.entities == []
    assert result.report.valid_rows == 0
    assert any(
        i.field == "client_id" and i.issue_code == IssueCode.MISSING_REQUIRED_FIELD
        for i in result.issues
    )


def test_blank_client_name_is_invalid(tmp_path: Path) -> None:
    _write_csv(tmp_path, "k.csv", [_row(client_name="")])
    result = _ingest(tmp_path, "k.csv")
    assert result.report.valid_rows == 0
    assert any(
        i.field == "client_name" and i.issue_code == IssueCode.MISSING_REQUIRED_FIELD
        for i in result.issues
    )


# --------------------------------------------------------------------------- #
# 12. Valid boolean normalization (incl. bool("False") pitfall)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "token,expected",
    [("0", False), ("1", True), ("true", True), ("False", False),
     ("YES", True), ("no", False), ("Y", True), ("n", False)],
)
def test_boolean_normalization(token: str, expected: bool) -> None:
    assert normalize_bool(token) is expected


def test_valid_boolean_flags_ingest(tmp_path: Path) -> None:
    _write_csv(tmp_path, "k.csv",
               [_row(client_id="1", pep_flag="true", sanctions_flag="0",
                     fatf_country_flag="Yes")])
    e = _ingest(tmp_path, "k.csv").entities[0]
    assert e.pep_flag is True and e.sanctions_flag is False and e.fatf_country_flag is True


# --------------------------------------------------------------------------- #
# 13. Invalid boolean value handling
# --------------------------------------------------------------------------- #
def test_invalid_boolean_is_flagged_not_coerced(tmp_path: Path) -> None:
    _write_csv(tmp_path, "k.csv", [_row(client_id="1", pep_flag="maybe")])
    result = _ingest(tmp_path, "k.csv")
    assert result.report.valid_rows == 0
    assert any(i.issue_code == IssueCode.INVALID_BOOLEAN for i in result.issues)


# --------------------------------------------------------------------------- #
# 14. Sector-risk normalization
# --------------------------------------------------------------------------- #
def test_sector_risk_categories_normalized(tmp_path: Path) -> None:
    _write_csv(tmp_path, "k.csv", [
        _row(client_id="1", sector_risk="High"),
        _row(client_id="2", sector_risk="medium"),
        _row(client_id="3", sector_risk="LOW"),
    ])
    levels = {e.client_id: e.sector_risk for e in _ingest(tmp_path, "k.csv").entities}
    assert levels == {
        "1": SectorRiskLevel.HIGH,
        "2": SectorRiskLevel.MEDIUM,
        "3": SectorRiskLevel.LOW,
    }


def test_invalid_sector_risk_is_flagged(tmp_path: Path) -> None:
    _write_csv(tmp_path, "k.csv", [_row(client_id="1", sector_risk="extreme")])
    result = _ingest(tmp_path, "k.csv")
    assert result.report.valid_rows == 0
    assert any(i.issue_code == IssueCode.INVALID_SECTOR_RISK for i in result.issues)


# --------------------------------------------------------------------------- #
# 15/16. Duplicate client_id detection; not silently overwritten
# --------------------------------------------------------------------------- #
def test_duplicate_client_ids_detected_and_not_emitted(tmp_path: Path) -> None:
    _write_csv(tmp_path, "k.csv", [
        _row(client_id="7", client_name="First"),
        _row(client_id="7", client_name="Second"),
        _row(client_id="8", client_name="Unique"),
    ])
    result = _ingest(tmp_path, "k.csv")
    # Only the unique id survives; neither duplicate is chosen as authoritative.
    assert result.report.duplicate_client_ids == 1
    assert [e.client_id for e in result.entities] == ["8"]
    dup_issues = [i for i in result.issues if i.issue_code == IssueCode.DUPLICATE_CLIENT_ID]
    assert len(dup_issues) == 2  # both occurrences flagged


# --------------------------------------------------------------------------- #
# 17. Excessively long field rejection
# --------------------------------------------------------------------------- #
def test_excessively_long_field_flagged(tmp_path: Path) -> None:
    _write_csv(tmp_path, "k.csv", [_row(client_id="1", client_name="A" * 500)])
    result = _ingest(tmp_path, "k.csv")
    assert result.report.valid_rows == 0
    assert any(i.issue_code == IssueCode.VALUE_TOO_LONG for i in result.issues)


# --------------------------------------------------------------------------- #
# 19. aliases defaults are not shared
# --------------------------------------------------------------------------- #
def test_aliases_defaults_not_shared(tmp_path: Path) -> None:
    _write_csv(tmp_path, "k.csv", [_row(client_id="1"), _row(client_id="2")])
    entities = _ingest(tmp_path, "k.csv").entities
    entities[0].aliases.append("X")
    assert entities[1].aliases == []


# --------------------------------------------------------------------------- #
# 20. Data-quality report counts are correct
# --------------------------------------------------------------------------- #
def test_data_quality_report_counts(tmp_path: Path) -> None:
    _write_csv(tmp_path, "k.csv", [
        _row(client_id="1"),                       # valid
        _row(client_id="2"),                       # valid
        _row(client_id="3", pep_flag="maybe"),     # invalid boolean
        _row(client_id="4", client_name=""),       # missing name
    ])
    r = _ingest(tmp_path, "k.csv").report
    assert r.total_rows == 4
    assert r.valid_rows == 2
    assert r.invalid_rows == 2
    assert r.validation_issue_counts.get("invalid_boolean") == 1
    assert r.missing_required_field_counts.get("client_name") == 1


# --------------------------------------------------------------------------- #
# 21. Validation issues do not contain full raw rows / raw PII
# --------------------------------------------------------------------------- #
def test_validation_issue_has_no_raw_row_or_name(tmp_path: Path) -> None:
    fields = set(ValidationIssue.model_fields)
    assert "row" not in fields and "raw" not in fields and "client_name" not in fields
    assert fields == {"row_number", "field", "issue_code", "message", "client_ref"}

    _write_csv(tmp_path, "k.csv", [_row(client_id="1", client_name="Secret Name",
                                        pep_flag="maybe")])
    for issue in _ingest(tmp_path, "k.csv").issues:
        dumped = issue.model_dump()
        assert "Secret Name" not in str(dumped)  # raw name never leaks
