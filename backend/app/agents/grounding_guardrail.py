"""Grounding guardrail — verify that LLM-generated evidence citations
actually resolve to records in the loaded datasets.

Each ``source_id`` is parsed and checked against the appropriate data
loader cache.  Citations that cannot be resolved are stripped from the
model output and collected into an ``unverified`` list so the pipeline
can log or surface them without silently passing hallucinated evidence.

Supported source_id patterns
-----------------------------
KYC profile (source_type = kyc_profile):
    "client_id=3", "sector_risk=High", "pep_flag=1", or any key that
    exists on the client profile dict.

Transactions (source_type = transaction):
    Composite keys like "Date|Time|Sender|Receiver" or
    "txn:2022-11-16|11:24:26|2806740273|6829585528".  Also bare
    account numbers ("2806740273") found in Sender/Receiver columns.

Sanctions (source_type = sanctions_list):
    "ofac_sdn:ENTITY NAME", "OpenSanctions:ENTITY NAME", or a bare
    entity name that appears in the sanctions cache.

GDPR (source_type = gdpr):
    "article5", "GDPR Article 6", "article_id=article5".

For source types without a data-backed lookup (pep_registry,
open_source, llm_analysis), citations are passed through as-is — no
ground truth exists to check against.
"""

from __future__ import annotations

import logging
import re

from pydantic import BaseModel, Field

from app.schemas.common import EvidenceItem, SourceType
from app.schemas.findings import InvestigationFinding
from app.schemas.debate import DebateArgument
from app.schemas.sar import SARDraft

from app.data_loaders.kyc_loader import get_client_profile
from app.data_loaders.transaction_loader import (
    get_client_transactions,
    _load_transactions,
)
from app.data_loaders.sanctions_loader import _load as _load_sanctions
from app.data_loaders.gdpr_loader import get_gdpr_article_by_id

logger = logging.getLogger(__name__)

# ── Result wrapper ──────────────────────────────────────────────────

class UnverifiedCitation(BaseModel):
    claim: str
    source_id: str
    source_type: str
    reason: str


class GuardrailResult(BaseModel):
    verified_count: int = 0
    stripped_count: int = 0
    skipped_count: int = Field(
        0, description="Citations with source types that have no ground truth to check"
    )
    unverified: list[UnverifiedCitation] = Field(default_factory=list)


# ── Source-ID verifiers ─────────────────────────────────────────────

_PROFILE_FIELDS = {
    "client_id", "client_name", "client_type", "sector", "sector_risk",
    "country", "pep_flag", "sanctions_flag", "fatf_country_flag",
    "ofac_country_flag", "sectoral_sanctions_flag", "ownership_opacity_score",
}

_NO_CHECK_TYPES = {
    SourceType.PEP_REGISTRY,
    SourceType.OPEN_SOURCE,
    SourceType.LLM_ANALYSIS,
}


def _verify_kyc(source_id: str, client_id: int | None) -> tuple[bool, str]:
    if client_id is None:
        return False, "no client_id available for profile lookup"

    profile = get_client_profile(client_id)
    if profile is None:
        return False, f"no profile found for client_id={client_id}"

    sid = source_id.strip().lower()

    for field in _PROFILE_FIELDS:
        if field in sid:
            return True, ""

    if sid.replace("-", "").replace("_", "").isdigit():
        if str(client_id) in sid:
            return True, ""

    return False, f"'{source_id}' does not match any known profile field"


def _verify_transaction(source_id: str, client_id: int | None) -> tuple[bool, str]:
    sid = source_id.strip()

    # strip common prefixes the LLM might add
    for prefix in ("txn:", "transaction:", "tx:"):
        if sid.lower().startswith(prefix):
            sid = sid[len(prefix):]
            break

    txn_index = _load_transactions()

    # 1) check if it contains a recognisable account number
    numbers = re.findall(r"\d{6,}", sid)
    for num in numbers:
        if num in txn_index:
            return True, ""

    # 2) try parsing as Date|Time|Sender|Receiver composite key
    parts = re.split(r"[|/]", sid)
    if len(parts) >= 3:
        for part in parts:
            part = part.strip()
            if part in txn_index:
                return True, ""

    # 3) if we have client_id, check if any known transaction partially
    #    matches (date, amount, account substring)
    if client_id is not None:
        txns = get_client_transactions(client_id)
        for txn in txns:
            if txn["Date"] in sid or txn["Sender_account"] in sid or txn["Receiver_account"] in sid:
                return True, ""
            if str(txn["Amount"]) in sid:
                return True, ""

    return False, f"'{source_id}' does not match any transaction record"


def _verify_sanctions(source_id: str) -> tuple[bool, str]:
    sid = source_id.strip()

    # strip common prefixes
    for prefix in ("ofac_sdn:", "ofac:", "opensanctions:", "sanctions:"):
        if sid.lower().startswith(prefix):
            sid = sid[len(prefix):].strip()
            break

    if not sid:
        return False, "empty sanctions reference after stripping prefix"

    entries = _load_sanctions()
    sid_lower = sid.lower()

    _MIN_SUBSTR_LEN = 4

    for source, name, aliases, country, info in entries:
        name_lower = name.lower()
        if sid_lower == name_lower:
            return True, ""
        if len(sid_lower) >= _MIN_SUBSTR_LEN and sid_lower in name_lower:
            return True, ""
        if len(name_lower) >= _MIN_SUBSTR_LEN and name_lower in sid_lower:
            return True, ""
        if aliases and len(sid_lower) >= _MIN_SUBSTR_LEN and sid_lower in aliases.lower():
            return True, ""

    return False, f"'{source_id}' does not match any sanctions entry"


_ARTICLE_RE = re.compile(r"article\s*(\d+)", re.IGNORECASE)


def _verify_gdpr(source_id: str) -> tuple[bool, str]:
    sid = source_id.strip()

    m = _ARTICLE_RE.search(sid)
    if m:
        article_id = f"article{m.group(1)}"
        results = get_gdpr_article_by_id(article_id)
        if results:
            return True, ""
        return False, f"article '{article_id}' not found in GDPR data"

    # try as-is (e.g. "article5")
    results = get_gdpr_article_by_id(sid)
    if results:
        return True, ""

    return False, f"'{source_id}' does not match any GDPR article"


def _verify_source_id(
    source_type: SourceType,
    source_id: str,
    client_id: int | None,
) -> tuple[bool, str]:
    if source_type in _NO_CHECK_TYPES:
        return True, "no_ground_truth"

    if source_type == SourceType.KYC_PROFILE:
        return _verify_kyc(source_id, client_id)
    if source_type == SourceType.TRANSACTION:
        return _verify_transaction(source_id, client_id)
    if source_type == SourceType.SANCTIONS_LIST:
        return _verify_sanctions(source_id)
    if source_type == SourceType.GDPR:
        return _verify_gdpr(source_id)

    return True, "unknown_source_type"


# ── Public API ──────────────────────────────────────────────────────

def verify_finding(
    finding: InvestigationFinding,
) -> tuple[InvestigationFinding, GuardrailResult]:
    """Validate an InvestigationFinding's evidence citations.

    Returns a new InvestigationFinding with unverifiable evidence
    stripped, plus a GuardrailResult listing what was removed and why.
    """
    result = GuardrailResult()
    verified_evidence: list[EvidenceItem] = []

    for ev in finding.evidence:
        ok, reason = _verify_source_id(ev.source_type, ev.source_id, finding.client_id)

        if reason == "no_ground_truth":
            result.skipped_count += 1
            verified_evidence.append(ev)
        elif ok:
            result.verified_count += 1
            verified_evidence.append(ev)
        else:
            result.stripped_count += 1
            result.unverified.append(UnverifiedCitation(
                claim=ev.claim,
                source_id=ev.source_id,
                source_type=ev.source_type.value,
                reason=reason,
            ))
            logger.warning(
                "Stripped unverified evidence: source_id=%r reason=%s",
                ev.source_id, reason,
            )

    cleaned = finding.model_copy(update={"evidence": verified_evidence})
    return cleaned, result


def verify_debate_argument(
    argument: DebateArgument,
    finding: InvestigationFinding,
) -> tuple[DebateArgument, GuardrailResult]:
    """Validate a DebateArgument's cited_evidence references.

    Cross-references each ``cited_evidence`` entry against the
    ``source_id`` values that survived guardrail verification in the
    InvestigationFinding.  Citations that don't match any known
    source_id are stripped.
    """
    known_ids = {ev.source_id for ev in finding.evidence}
    result = GuardrailResult()
    verified_refs: list[str] = []

    for ref in argument.cited_evidence:
        if ref in known_ids:
            result.verified_count += 1
            verified_refs.append(ref)
        else:
            # fuzzy: check if the ref is a substring of or contains a known id
            matched = False
            for kid in known_ids:
                if ref in kid or kid in ref:
                    result.verified_count += 1
                    verified_refs.append(ref)
                    matched = True
                    break
            if not matched:
                result.stripped_count += 1
                result.unverified.append(UnverifiedCitation(
                    claim=argument.argument[:120],
                    source_id=ref,
                    source_type="debate_reference",
                    reason=f"'{ref}' not found in finding's verified evidence",
                ))
                logger.warning(
                    "Stripped unverified debate citation: %r", ref,
                )

    cleaned = argument.model_copy(update={"cited_evidence": verified_refs})
    return cleaned, result


def verify_sar(
    sar: SARDraft,
) -> tuple[SARDraft, GuardrailResult]:
    """Validate a SARDraft's evidence_appendix citations.

    Same logic as ``verify_finding`` — checks each ``EvidenceItem``
    against the real datasets.
    """
    result = GuardrailResult()
    verified_evidence: list[EvidenceItem] = []

    for ev in sar.evidence_appendix:
        ok, reason = _verify_source_id(ev.source_type, ev.source_id, sar.client_id)

        if reason == "no_ground_truth":
            result.skipped_count += 1
            verified_evidence.append(ev)
        elif ok:
            result.verified_count += 1
            verified_evidence.append(ev)
        else:
            result.stripped_count += 1
            result.unverified.append(UnverifiedCitation(
                claim=ev.claim,
                source_id=ev.source_id,
                source_type=ev.source_type.value,
                reason=reason,
            ))
            logger.warning(
                "Stripped unverified SAR evidence: source_id=%r reason=%s",
                ev.source_id, reason,
            )

    cleaned = sar.model_copy(update={"evidence_appendix": verified_evidence})
    return cleaned, result
