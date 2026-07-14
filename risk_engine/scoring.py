from __future__ import annotations

from statistics import mean
from typing import Any

from risk_engine.config import RiskEngineConfig
from risk_engine.schemas import ScoreComponent, SubFactor


HIGH_RISK_SECTORS = {"crypto", "gambling", "arms", "defense", "precious metals", "money services"}
HIGH_RISK_COUNTRIES = {"iran", "north korea", "myanmar", "syria", "russia"}
FATF_HIGH_RISK_COUNTRIES = {"iran", "north korea", "myanmar"}
TRUSTED_SOURCES = {"ofac sdn", "opensanctions", "government registry", "regulator", "reuters", "ap"}
UBO_RELATIONSHIPS = {"ubo", "beneficial owner", "director", "signatory", "shareholder"}


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "y", "1"}
    return bool(value)


def normalized_text(value: Any) -> str:
    return str(value or "").strip().lower()


def numeric(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def evidence_id(signal: dict[str, Any]) -> list[str]:
    value = signal.get("evidence_id") or signal.get("evidence_ids")
    if not value:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item]
    return [str(value)]


def make_factor(name: str, max_points: float, confidence: float, reason: str, evidence_ids: list[str] | None = None) -> SubFactor:
    clean_confidence = clamp(confidence, 0.0, 1.0)
    return SubFactor(
        name=name,
        max_points=max_points,
        confidence=clean_confidence,
        contribution=max_points * clean_confidence,
        reason=reason,
        evidence_ids=evidence_ids or [],
    )


def make_component(name: str, max_score: int, sub_factors: list[SubFactor]) -> ScoreComponent:
    score = clamp(sum(item.contribution for item in sub_factors), 0.0, float(max_score))
    return ScoreComponent(
        name=name,
        score=score,
        max_score=max_score,
        sub_factors=sub_factors,
        reasons=[item.reason for item in sub_factors],
        evidence_ids=_unique(evidence for item in sub_factors for evidence in item.evidence_ids),
        confidence_inputs=[item.confidence for item in sub_factors],
    )


def score_kyc_profile(kyc: dict[str, Any], config: RiskEngineConfig) -> ScoreComponent:
    factors: list[SubFactor] = []
    evidence = evidence_id(kyc)
    confidence = numeric(kyc.get("confidence"), 0.80)

    existing = normalized_text(kyc.get("existing_kyc_risk") or kyc.get("risk_rating"))
    if existing == "high":
        factors.append(make_factor("existing_kyc_high", 10, confidence, "Existing KYC profile is high risk", evidence))
    elif existing == "medium":
        factors.append(make_factor("existing_kyc_medium", 6, confidence, "Existing KYC profile is medium risk", evidence))
    elif existing == "low":
        factors.append(make_factor("existing_kyc_low", 2, confidence, "Existing KYC profile is low risk", evidence))

    if as_bool(kyc.get("pep_flag")):
        factors.append(make_factor("pep_flag", 7, numeric(kyc.get("pep_confidence"), confidence), "Customer or linked party is marked as PEP", evidence))

    sector = normalized_text(kyc.get("sector") or kyc.get("industry"))
    if sector in HIGH_RISK_SECTORS:
        factors.append(make_factor("high_risk_sector", 5, confidence, f"High-risk sector: {sector}", evidence))

    if as_bool(kyc.get("kyc_incomplete")) or as_bool(kyc.get("missing_documents")):
        factors.append(make_factor("incomplete_kyc", 3, confidence, "KYC profile has missing or incomplete documents", evidence))

    return make_component("kyc_profile_risk", config.weights.kyc_profile, factors)


def score_sanctions(sanctions: dict[str, Any], ownership: dict[str, Any], media: dict[str, Any], config: RiskEngineConfig) -> ScoreComponent:
    factors: list[SubFactor] = []
    sanctions_evidence = evidence_id(sanctions)
    ownership_evidence = evidence_id(ownership)
    media_evidence = evidence_id(media)

    if as_bool(sanctions.get("has_match")):
        confidence = numeric(sanctions.get("match_confidence", sanctions.get("confidence")), 0.50)
        relationship = normalized_text(sanctions.get("relationship"))
        source = normalized_text(sanctions.get("source"))

        if relationship in UBO_RELATIONSHIPS:
            factors.append(make_factor(
                "ubo_chain_sanctions_match",
                12,
                confidence,
                f"Sanctions match found for linked {relationship}",
                sanctions_evidence,
            ))
        else:
            factors.append(make_factor(
                "direct_entity_sanctions_match",
                18,
                confidence,
                "Direct entity sanctions match",
                sanctions_evidence,
            ))

        if source in {"ofac sdn", "opensanctions"}:
            factors.append(make_factor(
                "trusted_sanctions_source",
                4,
                min(confidence, 0.95),
                f"Sanctions source is authoritative: {source}",
                sanctions_evidence,
            ))

    if as_bool(ownership.get("sanctioned_ubo")):
        confidence = numeric(ownership.get("confidence"), 0.75)
        layers = int(numeric(ownership.get("shell_layers", ownership.get("ownership_layers")), 0))
        reason = "UBO-chain sanctions match found"
        if layers >= 2:
            reason = f"UBO-chain sanctions match found {layers} layer(s) deep"
        factors.append(make_factor("ownership_chain_sanctions_hit", 8, confidence, reason, ownership_evidence))

    if as_bool(media.get("negative_news_found")) and as_bool(media.get("mentions_sanctions")):
        confidence = numeric(media.get("confidence"), 0.55)
        factors.append(make_factor(
            "adverse_media_sanctions_mention",
            4,
            confidence,
            "Adverse media mentions sanctions exposure",
            media_evidence,
        ))

    return make_component("sanctions_risk", config.weights.sanctions, factors)


def score_transactions(transactions: dict[str, Any], config: RiskEngineConfig) -> ScoreComponent:
    factors: list[SubFactor] = []
    evidence = evidence_id(transactions)
    probability = numeric(transactions.get("suspicious_probability", transactions.get("anomaly_score")), 0.0)

    if probability:
        reason = "Transaction monitoring model reports suspicious activity probability"
        if probability >= 0.70:
            reason = "Transaction monitoring model reports high suspicious probability"
        elif probability >= 0.40:
            reason = "Transaction monitoring model reports moderate suspicious probability"
        factors.append(make_factor("transaction_model_probability", 14, probability, reason, evidence))

    volume_change = numeric(transactions.get("monthly_volume_change"), 0.0)
    volume_confidence = numeric(transactions.get("volume_confidence"), 0.85)
    if volume_change >= 3.0:
        factors.append(make_factor("volume_spike_3x", 4, volume_confidence, "Monthly transaction volume increased by 3x or more", evidence))
    elif volume_change >= 2.0:
        factors.append(make_factor("volume_spike_2x", 3, volume_confidence, "Monthly transaction volume increased by 2x or more", evidence))
    elif volume_change >= 1.5:
        factors.append(make_factor("volume_spike", 2, volume_confidence, "Monthly transaction volume increased materially", evidence))

    high_risk_transfers = int(numeric(transactions.get("high_risk_country_transfers"), 0))
    geo_confidence = numeric(transactions.get("geo_confidence"), 0.85)
    if high_risk_transfers >= 10:
        factors.append(make_factor("repeated_high_risk_jurisdiction_transfers", 4, geo_confidence, "Repeated transfers involving high-risk jurisdictions", evidence))
    elif high_risk_transfers >= 3:
        factors.append(make_factor("some_high_risk_jurisdiction_transfers", 2, geo_confidence, "Some transfers involve high-risk jurisdictions", evidence))

    typology_count = int(numeric(transactions.get("typology_hits"), 0))
    if typology_count:
        factors.append(make_factor(
            "aml_typology_hits",
            min(3, typology_count * 1.5),
            numeric(transactions.get("typology_confidence"), 0.80),
            f"{typology_count} AML typology signal(s) detected",
            evidence,
        ))

    return make_component("transaction_risk", config.weights.transactions, factors)


def score_adverse_media(media: dict[str, Any], config: RiskEngineConfig) -> ScoreComponent:
    factors: list[SubFactor] = []
    if not as_bool(media.get("negative_news_found")):
        return make_component("adverse_media_risk", config.weights.adverse_media, factors)

    evidence = evidence_id(media)
    confidence = numeric(media.get("confidence"), 0.65)
    severity = normalized_text(media.get("severity"))
    source = normalized_text(media.get("source"))
    source_count = int(numeric(media.get("source_count"), 1))
    recent_days = int(numeric(media.get("days_since_event"), 999))

    severity_points = {"low": 5, "medium": 8, "high": 11, "critical": 12}.get(severity, 6)
    factors.append(make_factor("media_severity", severity_points, confidence, f"{severity or 'Unknown'} adverse-media signal found", evidence))

    if source in TRUSTED_SOURCES:
        factors.append(make_factor("trusted_media_source", 1, min(confidence, 0.95), f"Source is treated as reliable: {source}", evidence))
    if source_count >= 2:
        factors.append(make_factor("media_corroboration", 1, confidence, "Adverse media is corroborated by multiple sources", evidence))
    if recent_days <= 30:
        factors.append(make_factor("recent_media_event", 1, confidence, "Adverse media event is recent", evidence))

    return make_component("adverse_media_risk", config.weights.adverse_media, factors)


def score_jurisdiction(payload: dict[str, Any], config: RiskEngineConfig) -> ScoreComponent:
    factors: list[SubFactor] = []
    country = normalized_text(payload.get("country"))
    if not country:
        country = normalized_text(payload.get("kyc", {}).get("country") if isinstance(payload.get("kyc"), dict) else "")

    jurisdiction = payload.get("jurisdiction", {}) if isinstance(payload.get("jurisdiction"), dict) else {}
    evidence = evidence_id(jurisdiction) or evidence_id(payload)
    confidence = numeric(payload.get("jurisdiction_confidence", jurisdiction.get("confidence")), 0.85)

    if country in FATF_HIGH_RISK_COUNTRIES or as_bool(payload.get("fatf_high_risk")):
        factors.append(make_factor("fatf_high_risk_jurisdiction", 5, confidence, "Customer is linked to FATF high-risk jurisdiction", evidence))
    elif country in HIGH_RISK_COUNTRIES or as_bool(payload.get("high_risk_country")):
        factors.append(make_factor("high_risk_jurisdiction", 3, confidence, "Customer is linked to high-risk jurisdiction", evidence))

    return make_component("jurisdiction_risk", config.weights.jurisdiction, factors)


def confirmed_sanctions_confidence(sanctions: dict[str, Any], ownership: dict[str, Any]) -> float:
    direct_confidence = numeric(sanctions.get("match_confidence", sanctions.get("confidence")), 0.0)
    ownership_confidence = numeric(ownership.get("confidence"), 0.0)

    if as_bool(sanctions.get("confirmed")) or normalized_text(sanctions.get("match_status")) == "confirmed":
        return direct_confidence
    if as_bool(ownership.get("sanctioned_ubo")):
        return ownership_confidence
    return 0.0


def confidence_score(components: list[ScoreComponent]) -> float:
    weighted_values: list[float] = []
    for component in components:
        for factor in component.sub_factors:
            if factor.contribution <= 0:
                continue
            weighted_values.append(factor.confidence * (factor.contribution / max(factor.max_points, 1)))

    if not weighted_values:
        return 0.85
    return max(0.0, min(1.0, mean(weighted_values) + 0.10))


def _unique(values: Any) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value)
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result