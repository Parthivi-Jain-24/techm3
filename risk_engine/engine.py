from __future__ import annotations

from datetime import datetime
from typing import Any

from risk_engine.config import RiskEngineConfig
from risk_engine.schemas import RiskAssessment, RiskLevel, RiskTrend, TimelineEvent
from risk_engine.scoring import (
    confidence_score,
    confirmed_sanctions_confidence,
    score_adverse_media,
    score_jurisdiction,
    score_kyc_profile,
    score_sanctions,
    score_transactions,
)


class RiskEngine:
    def __init__(self, config: RiskEngineConfig | None = None) -> None:
        self.config = config or RiskEngineConfig()

    def assess(self, payload: dict[str, Any]) -> RiskAssessment:
        customer_id = str(payload.get("customer_id") or payload.get("id") or "UNKNOWN_CUSTOMER")
        previous_score = int(payload.get("previous_score", 0))
        sanctions = _section(payload, "sanctions")
        ownership = _section(payload, "ownership")
        adverse_media = _section(payload, "adverse_media")

        components = [
            score_kyc_profile(_section(payload, "kyc"), self.config),
            score_sanctions(sanctions, ownership, adverse_media, self.config),
            score_transactions(_section(payload, "transactions"), self.config),
            score_adverse_media(adverse_media, self.config),
            score_jurisdiction(payload, self.config),
        ]

        base_score = round(min(100.0, sum(component.score for component in components)))
        risk_score, escalation_floor, applied_overrides = self._apply_escalation_floor(base_score, sanctions, ownership)
        confidence = confidence_score(components)
        risk_delta = risk_score - previous_score
        risk_level = self._risk_level(risk_score)
        risk_trend = self._risk_trend(risk_delta)
        velocity = self._velocity(payload, risk_score)
        evidence_ids = _unique(item for component in components for item in component.evidence_ids)
        top_reasons = self._top_reasons(components)

        sar_recommended = (
            risk_score >= self.config.thresholds.sar
            and confidence >= self.config.thresholds.minimum_sar_confidence
        )

        timeline_event = TimelineEvent(
            customer_id=customer_id,
            previous_score=previous_score,
            new_score=risk_score,
            change=risk_delta,
            reason=top_reasons[0] if top_reasons else "Risk score recalculated",
            evidence_ids=evidence_ids,
            confidence=confidence,
            model_version=self.config.model_version,
        )

        return RiskAssessment(
            customer_id=customer_id,
            risk_score=risk_score,
            base_score=base_score,
            risk_level=risk_level,
            confidence_score=confidence,
            risk_delta=risk_delta,
            risk_trend=risk_trend,
            velocity=velocity,
            escalation_floor=escalation_floor,
            applied_overrides=applied_overrides,
            trigger_investigation=risk_score >= self.config.thresholds.investigation,
            sar_recommended=sar_recommended,
            breakdown={component.name: component.score for component in components},
            component_details=components,
            evidence_ids=evidence_ids,
            top_reasons=top_reasons,
            timeline_event=timeline_event,
            model_version=self.config.model_version,
        )

    def _apply_escalation_floor(self, base_score: int, sanctions: dict[str, Any], ownership: dict[str, Any]) -> tuple[int, int | None, list[str]]:
        sanctions_confidence = confirmed_sanctions_confidence(sanctions, ownership)
        if sanctions_confidence >= 0.85:
            floor = self.config.thresholds.high_confidence_sanctions_floor
            return max(base_score, floor), floor, ["High-confidence confirmed sanctions match applies hard escalation floor"]
        if sanctions_confidence >= 0.60:
            floor = self.config.thresholds.medium_confidence_sanctions_floor
            return max(base_score, floor), floor, ["Confirmed sanctions match applies investigation floor"]
        return base_score, None, []

    def _risk_level(self, score: int) -> RiskLevel:
        if score >= self.config.thresholds.critical:
            return RiskLevel.CRITICAL
        if score >= self.config.thresholds.high:
            return RiskLevel.HIGH
        if score >= self.config.thresholds.medium:
            return RiskLevel.MEDIUM
        return RiskLevel.LOW

    @staticmethod
    def _risk_trend(delta: int) -> RiskTrend:
        if delta >= 5:
            return RiskTrend.RISING
        if delta <= -5:
            return RiskTrend.FALLING
        return RiskTrend.STABLE

    def _velocity(self, payload: dict[str, Any], current_score: int) -> dict[str, Any]:
        historical_score = payload.get("score_n_days_ago")
        n_days = payload.get("n_days")

        if historical_score is None or n_days is None:
            historical_score, n_days = self._from_score_history(payload.get("score_history", []))

        if historical_score is None or not n_days:
            return {
                "points_per_day": None,
                "window_days": None,
                "days_to_high": None,
                "days_to_critical": None,
            }

        historical_score = int(historical_score)
        n_days = max(float(n_days), 1.0)
        points_per_day = (current_score - historical_score) / n_days

        return {
            "points_per_day": round(points_per_day, 4),
            "window_days": round(n_days, 2),
            "days_to_high": self._days_to_threshold(current_score, points_per_day, self.config.thresholds.high),
            "days_to_critical": self._days_to_threshold(current_score, points_per_day, self.config.thresholds.critical),
        }

    @staticmethod
    def _from_score_history(score_history: Any) -> tuple[int | None, float | None]:
        if not isinstance(score_history, list) or not score_history:
            return None, None

        earliest = score_history[0]
        latest = score_history[-1]
        if not isinstance(earliest, dict) or not isinstance(latest, dict):
            return None, None

        historical_score = earliest.get("score")
        earliest_time = earliest.get("timestamp")
        latest_time = latest.get("timestamp")
        if historical_score is None:
            return None, None
        if not earliest_time or not latest_time:
            return historical_score, max(len(score_history) - 1, 1)

        try:
            start = datetime.fromisoformat(str(earliest_time).replace("Z", "+00:00"))
            end = datetime.fromisoformat(str(latest_time).replace("Z", "+00:00"))
        except ValueError:
            return historical_score, max(len(score_history) - 1, 1)

        days = max((end - start).total_seconds() / 86400, 1.0)
        return historical_score, days

    @staticmethod
    def _days_to_threshold(current_score: int, points_per_day: float, threshold: int) -> float | None:
        if points_per_day <= 0 or current_score >= threshold:
            return None
        return round((threshold - current_score) / points_per_day, 2)

    @staticmethod
    def _top_reasons(components: list[Any], limit: int = 5) -> list[str]:
        sub_factors = [factor for component in components for factor in component.sub_factors]
        ordered = sorted(sub_factors, key=lambda factor: factor.contribution, reverse=True)
        return [f"+{factor.contribution:.1f} pts: {factor.reason} ({factor.confidence:.0%} confidence)" for factor in ordered[:limit]]


def _section(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    return value if isinstance(value, dict) else {}


def _unique(values: Any) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value)
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result