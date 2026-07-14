# Risk Engine Integration Contract

The Risk Engine accepts one customer signal payload and returns an explainable, confidence-weighted risk assessment.

## Design Rules

- Risk and confidence remain separate outputs.
- Category scores are calculated from sub-factors: `sub_factor_points * sub_factor_confidence`.
- Confirmed sanctions hits apply hard escalation floors so they cannot be diluted by otherwise clean behavior.
- Velocity is reported separately and is not added into the score.
- Every material score contribution carries evidence IDs where available.

## Endpoint Shape

If wrapped in FastAPI:

```text
POST /risk/assess
```

If imported directly:

```python
from risk_engine import RiskEngine

assessment = RiskEngine().assess(payload).to_dict()
```

## Input Payload

```json
{
  "customer_id": "CUST-2041",
  "previous_score": 52,
  "score_n_days_ago": 56,
  "n_days": 21,
  "kyc": {
    "sector": "Crypto",
    "country": "UAE",
    "existing_kyc_risk": "MEDIUM",
    "pep_flag": false,
    "confidence": 0.8,
    "evidence_id": "EVD-101"
  },
  "sanctions": {
    "has_match": true,
    "match_confidence": 0.94,
    "relationship": "UBO",
    "source": "OFAC SDN",
    "evidence_id": "EVD-203"
  },
  "transactions": {
    "suspicious_probability": 0.76,
    "monthly_volume_change": 2.8,
    "high_risk_country_transfers": 12,
    "typology_hits": 2,
    "evidence_id": "EVD-311"
  },
  "adverse_media": {
    "negative_news_found": true,
    "severity": "HIGH",
    "source": "Reuters",
    "source_count": 2,
    "days_since_event": 3,
    "confidence": 0.82,
    "evidence_id": "EVD-407"
  },
  "ownership": {
    "sanctioned_ubo": true,
    "shell_layers": 3,
    "tax_haven_link": true,
    "confidence": 0.91,
    "evidence_id": "EVD-501"
  },
  "fatf_high_risk": true
}
```

## Output Highlights

```json
{
  "customer_id": "CUST-2041",
  "risk_score": 85,
  "base_score": 66,
  "risk_level": "CRITICAL",
  "confidence_score": 0.8107,
  "risk_delta": 33,
  "risk_trend": "RISING",
  "velocity": {
    "points_per_day": 1.381,
    "window_days": 21,
    "days_to_high": null,
    "days_to_critical": null
  },
  "escalation_floor": 85,
  "applied_overrides": [
    "High-confidence confirmed sanctions match applies hard escalation floor"
  ],
  "trigger_investigation": true,
  "sar_recommended": true,
  "breakdown": {
    "kyc_profile_risk": 8.8,
    "sanctions_risk": 22.32,
    "transaction_risk": 18.99,
    "adverse_media_risk": 11.48,
    "jurisdiction_risk": 4.25
  },
  "top_reasons": [
    "+11.3 pts: Sanctions match found for linked ubo (94% confidence)",
    "+10.6 pts: Transaction monitoring model reports high suspicious probability (76% confidence)"
  ],
  "model_version": "risk-engine-v2.0"
}
```

## Teammate Responsibilities

Secure Data and Identity should provide `kyc`, jurisdiction flags, `previous_score`, and historical score data if available.

Entity Intelligence should provide `sanctions` and `ownership` with evidence IDs and confidence values.

Transaction Monitoring should provide `transactions`. If the ML model is not ready, send rule-derived values such as `monthly_volume_change`, `high_risk_country_transfers`, and `typology_hits`.

Agent Orchestration should trigger investigation when `trigger_investigation` is true and request SAR drafting only when `sar_recommended` is true.

Frontend should display `risk_score`, `base_score`, `escalation_floor`, `breakdown`, `component_details.sub_factors`, `top_reasons`, and `velocity`.

Audit Trail should persist the full returned assessment, especially `timeline_event`, `model_version`, `evidence_ids`, and `applied_overrides`.