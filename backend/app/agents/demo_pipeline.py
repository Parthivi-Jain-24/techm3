"""Deterministic local outputs for the demo prototype.

These helpers let the UI exercise the full investigation, debate, SAR,
grounding, and privacy flow without requiring external LLM services or every
production CSV to be present. Set LLM_MODE=provider to use the real agents.
"""

from __future__ import annotations

from app.data_loaders import get_client_profile, get_client_transactions
from app.schemas.common import ConfidenceLevel, EvidenceItem, RiskLevel, SourceType
from app.schemas.debate import DebateArgument, DebatePosition, DebateVerdict, Verdict
from app.schemas.findings import InvestigationFinding, RiskIndicator
from app.schemas.sar import SARDraft


def _as_dict(value):
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "dict"):
        return value.dict()
    return {}


def _profile(client_id: int) -> dict:
    try:
        return _as_dict(get_client_profile(client_id))
    except FileNotFoundError:
        return {
            "client_id": client_id,
            "name": f"Demo Client {client_id}",
            "customer_type": "individual",
            "jurisdiction": "Demo jurisdiction",
            "sector_risk": "medium",
            "pep_flag": False,
            "sanctions_flag": client_id == 2041,
            "fatf_country_flag": False,
            "sectoral_sanctions_flag": False,
        }


def _transactions(client_id: int) -> list[dict]:
    try:
        return [_as_dict(row) for row in get_client_transactions(client_id)]
    except FileNotFoundError:
        return []


def _source_type(name: str):
    return getattr(SourceType, name.upper(), name)


def _risk_level(name: str):
    return getattr(RiskLevel, name.upper(), name)


def _confidence(name: str):
    return getattr(ConfidenceLevel, name.upper(), name)


def _evidence(claim: str, source_type, source_id: str, confidence="medium") -> EvidenceItem:
    return EvidenceItem(
        claim=claim,
        source_type=source_type,
        source_id=source_id,
        confidence=_confidence(confidence),
    )


def _indicator(indicator: str, severity: str, detail: str) -> RiskIndicator:
    return RiskIndicator(indicator=indicator, severity=_risk_level(severity), detail=detail)


def demo_finding(client_id: int) -> InvestigationFinding:
    profile = _profile(client_id)
    transactions = _transactions(client_id)
    name = profile.get("name") or profile.get("client_name") or f"Client {client_id}"

    evidence: list[EvidenceItem] = []
    indicators: list[RiskIndicator] = []

    sector_risk = str(profile.get("sector_risk", "")).lower()
    if sector_risk in {"high", "critical"}:
        indicators.append(_indicator("sector_risk", "high", f"Profile sector risk is {sector_risk}."))
        evidence.append(_evidence("High sector risk on KYC profile.", _source_type("kyc_profile"), "sector_risk=high", "high"))

    flag_map = {
        "sanctions_flag": "Possible sanctions exposure is present in profile flags.",
        "pep_flag": "Politically exposed person flag is present in profile.",
        "fatf_country_flag": "FATF high-risk jurisdiction flag is present in profile.",
        "sectoral_sanctions_flag": "Sectoral sanctions flag is present in profile.",
    }
    for key, detail in flag_map.items():
        if bool(profile.get(key)):
            severity = "critical" if key == "sanctions_flag" else "high"
            indicators.append(_indicator(key, severity, detail))
            evidence.append(_evidence(detail, _source_type("kyc_profile"), key, "high"))

    if transactions:
        largest = max(transactions, key=lambda row: float(row.get("Amount") or row.get("amount") or 0))
        amount = largest.get("Amount") or largest.get("amount") or "unknown"
        sender = largest.get("Sender_account") or largest.get("sender_account") or largest.get("account") or "transaction_record"
        indicators.append(_indicator("transaction_review", "medium", f"Largest observed transaction amount is {amount}."))
        evidence.append(_evidence(f"Largest observed transaction amount is {amount}.", _source_type("transaction"), f"txn:{sender}", "medium"))

    if not indicators:
        indicators.append(_indicator("baseline_review", "low", "No high-risk demo indicators were found in currently available local records."))
        evidence.append(_evidence("Profile was available for baseline KYC review.", _source_type("kyc_profile"), "client_id", "medium"))

    summary = f"Demo review for {name}: " + "; ".join(item.detail for item in indicators[:3])
    confidence = "high" if any(str(item.severity).lower().endswith(("high", "critical")) for item in indicators) else "medium"

    return InvestigationFinding(
        client_id=client_id,
        summary=summary,
        risk_indicators=indicators,
        evidence=evidence,
        confidence=_confidence(confidence),
    )


def demo_debate(finding: InvestigationFinding):
    source_ids = [item.source_id for item in finding.evidence]
    elevated = any(str(item.severity).lower().endswith(("high", "critical")) for item in finding.risk_indicators)

    prosecution = DebateArgument(
        position=DebatePosition.RISK_CONFIRMED,
        argument="The available verified indicators support escalation for compliance review.",
        cited_evidence=source_ids,
        strength=_confidence("high" if elevated else "medium"),
    )
    defense = DebateArgument(
        position=DebatePosition.FALSE_POSITIVE,
        argument="The case should remain proportionate because this is a demo review and only verified local evidence should drive action.",
        cited_evidence=source_ids[:1],
        strength=_confidence("medium"),
    )
    verdict = DebateVerdict(
        verdict=Verdict.ESCALATE_TO_SAR if elevated else Verdict.FALSE_POSITIVE_CLEAR,
        reasoning="Demo judge decision based only on the surviving verified evidence from the investigation stage.",
        confidence=_confidence("medium"),
        key_deciding_evidence=source_ids,
    )
    return prosecution, defense, verdict


def demo_sar(finding: InvestigationFinding, verdict: DebateVerdict) -> SARDraft:
    profile = _profile(finding.client_id)
    name = profile.get("name") or profile.get("client_name") or f"Client {finding.client_id}"
    jurisdiction = profile.get("jurisdiction") or profile.get("country") or "Demo jurisdiction"
    appendix = list(finding.evidence)
    cited = ", ".join(item.source_id for item in appendix) or "verified demo evidence"

    return SARDraft(
        client_id=finding.client_id,
        subject_information=f"Subject: {name}; jurisdiction: {jurisdiction}; client id: {finding.client_id}.",
        narrative=f"AI-generated demo SAR draft. The review identified indicators requiring human compliance review. Deciding evidence: {cited}.",
        red_flags=[item.detail for item in finding.risk_indicators],
        regulatory_basis=["Generic AML suspicious activity review obligation"],
        evidence_appendix=appendix,
        recommended_action="file SAR" if verdict.verdict == Verdict.ESCALATE_TO_SAR else "enhanced monitoring",
        disclaimer="AI-generated, requires human review before filing.",
    )
