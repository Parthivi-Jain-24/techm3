"""Phase 3 tests: context-aware minimization, masking-vs-omission, safety."""

from __future__ import annotations

import json

import pytest

from app.privacy.contexts import ProcessingContext
from app.privacy.errors import UnknownProcessingContextError
from app.privacy.minimization import (
    minimize_kyc_entity,
    to_agent_safe_dict,
    to_log_safe_dict,
)
from app.privacy.minimization.policies import CANONICAL_FIELDS
from app.schemas.kyc import NormalizedKYCEntity

KEY = "unit-test-key"


def _entity(**overrides) -> NormalizedKYCEntity:
    data = dict(
        client_id="123456",
        client_name="John Smith",
        client_type="Individual",
        country="IN",
        sector="Tech",
        sector_risk="high",
        pep_flag=True,
        sanctions_flag=True,
        fatf_country_flag=True,
        aliases=["Johnny S"],
    )
    data.update(overrides)
    return NormalizedKYCEntity(**data)


# --- 10. LOGGING removes unnecessary fields ------------------------------ #
def test_logging_omits_name_aliases_and_sensitive_flags() -> None:
    out = to_log_safe_dict(_entity(), pseudonymize_key=KEY)
    for forbidden in ("client_name", "aliases", "pep_flag", "sanctions_flag"):
        assert forbidden not in out
    assert out["client_id"].startswith("anon_")  # pseudonymized, not raw


# --- 11. ENTITY_SCREENING keeps matching fields -------------------------- #
def test_entity_screening_keeps_matching_fields() -> None:
    out = minimize_kyc_entity(_entity(), ProcessingContext.ENTITY_SCREENING)
    for needed in ("client_id", "client_name", "aliases", "country", "client_type"):
        assert needed in out
    assert out["client_id"] == "123456"  # raw id needed to correlate
    # risk/compliance signals are NOT part of identity resolution
    for absent in ("pep_flag", "sanctions_flag", "sector_risk"):
        assert absent not in out


# --- 12 & 29. AGENT_CONTEXT minimized; never the full record ------------- #
def test_agent_context_is_minimized_by_default() -> None:
    out = to_agent_safe_dict(_entity(), pseudonymize_key=KEY)
    assert "client_name" not in out and "aliases" not in out
    assert len(out) < len(CANONICAL_FIELDS)
    assert out["client_id"].startswith("anon_")


# --- 13. EXTERNAL_RESPONSE conservative ---------------------------------- #
def test_external_response_is_conservative() -> None:
    out = minimize_kyc_entity(_entity(), ProcessingContext.EXTERNAL_RESPONSE, KEY)
    assert set(out.keys()) <= {"client_id", "client_type"}
    assert "client_name" not in out and "aliases" not in out


# --- 14. omission vs masking --------------------------------------------- #
def test_disallowed_fields_are_omitted_not_masked() -> None:
    out = to_log_safe_dict(_entity(), pseudonymize_key=KEY)
    # client_name is not permitted in LOGGING at all -> the KEY is absent,
    # not merely present-with-a-masked-value.
    assert "client_name" not in out


# --- fail-closed ---------------------------------------------------------- #
def test_unknown_context_fails_closed() -> None:
    with pytest.raises(UnknownProcessingContextError):
        minimize_kyc_entity(_entity(), "not_a_real_context")  # type: ignore[arg-type]


# --- 20. immutability ----------------------------------------------------- #
def test_original_entity_not_mutated() -> None:
    entity = _entity()
    before = entity.model_dump()
    for ctx in ProcessingContext:
        minimize_kyc_entity(entity, ctx, pseudonymize_key=KEY)
    assert entity.model_dump() == before


# --- 25/26/27. log-safe representation ----------------------------------- #
def test_log_safe_has_no_raw_identity() -> None:
    out = to_log_safe_dict(_entity(), pseudonymize_key=KEY)
    blob = json.dumps(out)
    assert "John Smith" not in blob and "Johnny S" not in blob and "123456" not in blob
    assert len(out) <= 4  # not the entire 12-field entity


# --- 28. agent-safe only permitted fields -------------------------------- #
def test_agent_safe_only_permitted_fields() -> None:
    out = to_agent_safe_dict(_entity(), pseudonymize_key=KEY)
    assert set(out.keys()) <= {"client_id", "client_type", "country", "sector_risk"}


# --- Part J. safe serialization ------------------------------------------ #
def test_all_contexts_serialize_to_json() -> None:
    entity = _entity()
    for ctx in ProcessingContext:
        out = minimize_kyc_entity(entity, ctx, pseudonymize_key=KEY)
        json.dumps(out)  # must not raise; no enum/datetime/model leakage
        for value in out.values():
            assert isinstance(value, (str, bool, int, float, list, type(None)))
