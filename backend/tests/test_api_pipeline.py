"""Phase 5 tests: payload extraction, reuse of Phase 2 normalization + Phase 3 privacy."""

from __future__ import annotations

import asyncio
import logging

import pytest

from app.ingestion.api.errors import ApiErrorCode, ApiIngestionError
from app.ingestion.api.extraction import extract_records, map_records
from app.ingestion.api.models import PayloadLocation
from app.ingestion.pipelines.api_ingestion_pipeline import run_api_ingestion
from app.privacy import to_log_safe_dict
from app.privacy.classification import classify
from app.schemas.kyc import NormalizedKYCEntity, SectorRiskLevel
from tests._api_helpers import (
    FIELD_MAPPING,
    json_transport,
    make_connector,
    make_source,
    sample_record,
)


def run(coro):
    return asyncio.run(coro)


# --- extraction (43-47) -------------------------------------------------- #
def test_root_list_extraction() -> None:  # 43
    src = make_source(payload_location=PayloadLocation.ROOT_LIST)
    assert extract_records([{"a": 1}, {"b": 2}], src) == [{"a": 1}, {"b": 2}]


def test_data_field_extraction() -> None:  # 44
    src = make_source(payload_location=PayloadLocation.DATA_FIELD, data_field="data")
    assert extract_records({"data": [{"a": 1}]}, src) == [{"a": 1}]


def test_unexpected_shape_rejected() -> None:  # 45
    src = make_source(payload_location=PayloadLocation.ROOT_LIST)
    for bad in ({"not": "a list"}, "string", 42, [{"a": 1}, "notdict"]):
        with pytest.raises(ApiIngestionError) as e:
            extract_records(bad, src)
        assert e.value.code is ApiErrorCode.INVALID_PAYLOAD_SHAPE


def test_missing_data_field_rejected() -> None:  # 46
    src = make_source(payload_location=PayloadLocation.DATA_FIELD, data_field="data")
    with pytest.raises(ApiIngestionError) as e:
        extract_records({"other": []}, src)
    assert e.value.code is ApiErrorCode.INVALID_PAYLOAD_SHAPE


def test_no_arbitrary_expression_engine() -> None:  # 47
    # Only two small typed shapes; no JSONPath / expression evaluation exists.
    assert {p.value for p in PayloadLocation} == {"root_list", "data_field"}


# --- explicit mapping (48) ----------------------------------------------- #
def test_explicit_source_to_canonical_mapping() -> None:  # 48
    header, rows = map_records([sample_record()], FIELD_MAPPING)
    assert set(header) >= {"client_id", "client_name", "country"}
    assert rows[0]["client_id"] == "1" and rows[0]["client_name"] == "John Smith"


# --- normalization reuse (49-55) ----------------------------------------- #
def _ingest(records, **src_over):
    conn = make_connector(json_transport(records))
    return run(run_api_ingestion(make_source(**src_over), conn))


def test_valid_record_produces_normalized_entity() -> None:  # 49, 55
    res = _ingest([sample_record(customerId="1", iso="in", risk="High")])
    assert len(res.entities) == 1
    e = res.entities[0]
    assert isinstance(e, NormalizedKYCEntity)
    assert e.country == "IN"  # Phase 2 normalization (uppercased) reused
    assert e.sector_risk is SectorRiskLevel.HIGH


def test_missing_client_id_rejected() -> None:  # 50
    res = _ingest([sample_record(customerId="")])
    assert res.entities == []
    assert res.report.missing_required_field_counts.get("client_id") == 1


def test_invalid_boolean_rejected() -> None:  # 51
    res = _ingest([sample_record(pep="maybe")])
    assert res.entities == []
    assert res.report.validation_issue_counts.get("invalid_boolean") == 1


def test_excessive_length_rejected() -> None:  # 52
    res = _ingest([sample_record(fullName="A" * 500)])
    assert res.entities == []
    assert res.report.validation_issue_counts.get("value_too_long") == 1


def test_duplicate_client_id_detected_not_overwritten() -> None:  # 53, 54
    res = _ingest([
        sample_record(customerId="7", fullName="First"),
        sample_record(customerId="7", fullName="Second"),
        sample_record(customerId="9", fullName="Unique"),
    ])
    assert res.report.duplicate_client_ids == 1
    assert [e.client_id for e in res.entities] == ["9"]  # no silent winner


def test_schema_failure_when_required_field_unmapped() -> None:  # (schema reuse)
    partial = {k: v for k, v in FIELD_MAPPING.items() if v != "client_id"}
    with pytest.raises(ApiIngestionError) as e:
        _ingest([sample_record()], field_mapping=partial)
    assert e.value.code is ApiErrorCode.SCHEMA_VALIDATION_FAILED


# --- privacy integration (56-58) ----------------------------------------- #
def test_connector_does_not_log_full_payload(caplog) -> None:  # 56
    conn = make_connector(json_transport([sample_record(fullName="Very Secret Name")]))
    with caplog.at_level(logging.DEBUG):
        run(run_api_ingestion(make_source(), conn))
    blob = " ".join(r.getMessage() for r in caplog.records)
    assert "Very Secret Name" not in blob


def test_api_entity_still_covered_by_phase3_classification() -> None:  # 57
    res = _ingest([sample_record(customerId="1")])
    entity = res.entities[0]
    for field in type(entity).model_fields:  # every field has a classification
        assert classify(field) is not None


def test_log_safe_representation_usable_on_api_entity() -> None:  # 58
    res = _ingest([sample_record(customerId="1", fullName="John Smith")])
    safe = to_log_safe_dict(res.entities[0], pseudonymize_key="k")
    assert "client_name" not in safe  # Phase 3 minimization applies to API data
    assert "John Smith" not in str(safe)
