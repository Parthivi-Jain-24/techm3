# Risk Intelligence Engine Memory

This file is the team handoff note for the Risk Intelligence Engineering module.

## Purpose

The Risk Intelligence Engine converts KYC, sanctions, transaction, ownership, jurisdiction, and adverse-media signals into an explainable customer risk assessment.

It is designed for regulated compliance use:

- Risk score and confidence score are separate.
- Every score contribution is explainable through sub-factors.
- Evidence IDs are carried through the output.
- Confirmed sanctions hits apply hard escalation floors.
- Velocity/trend is reported separately and is not mixed into the risk score.
- Human review is required before report/SAR sign-off.

## Main Files

```text
risk_engine/engine.py              Main RiskEngine.assess(payload) entry point
risk_engine/scoring.py             Confidence-weighted scoring logic
risk_engine/schemas.py             RiskAssessment, ScoreComponent, SubFactor models
risk_engine/config.py              Weights, thresholds, model version
risk_engine/data_repository.py     Local CSV dataset loader and payload builder
risk_engine/governance.py          Case queue, review workflow, SAR sign-off, audit log
risk_engine/news_service.py        Optional NewsAPI adverse-media lookup
risk_engine/api.py                 FastAPI app and routes
frontend/app.js                    React governance dashboard
frontend/styles.css                Dashboard styling
docs/integration_contract.md       API payload/output contract
tests/                             Unit and API tests
```

## Current Formula

Category scores are confidence-weighted:

```text
category_score = sum(sub_factor_points * sub_factor_confidence)
```

Current category weights:

```text
KYC Profile Risk     0-25
Sanctions Risk       0-30
Transaction Risk     0-25
Adverse Media Risk   0-15
Jurisdiction Risk    0-5
Total                0-100
```

Important: UBO/ownership sanctions are handled inside `sanctions_risk`, not as a separate top-level category.

## Escalation Floors

A confirmed sanctions hit cannot be diluted by otherwise clean behavior.

```text
confirmed sanctions confidence >= 0.85 -> final score at least 85
confirmed sanctions confidence >= 0.60 -> final score at least 65
```

The engine returns both:

```text
base_score   Weighted confidence-adjusted score
risk_score   Final score after compliance escalation floors
```

## Dataset Integration

The engine reads local datasets from:

```text
data/challenge-3-dataset/kyc_profiles/clients_with_fatf_ofac.csv
data/challenge-3-dataset/kyc_profiles/transactions_with_fatf_ofac.csv
data/challenge-3-dataset/aml_transactions/SAML-D.csv
```

Current dataset usage:

- `clients_with_fatf_ofac.csv` drives customer KYC profile, sector risk, PEP, sanctions, FATF/OFAC flags, and ownership opacity.
- `transactions_with_fatf_ofac.csv` is grouped by `client_id` and converted into transaction risk signals.
- `SAML-D.csv` is recognized as a large AML transaction dataset; the app reports its row count/availability without loading all 9.5M rows into memory on every request.

## Input Payload Shape

Other modules can call the engine directly:

```python
from risk_engine import RiskEngine

assessment = RiskEngine().assess(payload).to_dict()
```

Typical payload:

```json
{
  "customer_id": "828",
  "previous_score": 48,
  "score_n_days_ago": 40,
  "n_days": 21,
  "kyc": {
    "sector": "Crypto",
    "country": "UAE",
    "existing_kyc_risk": "High",
    "pep_flag": false,
    "confidence": 0.88,
    "evidence_id": "KYC-828"
  },
  "sanctions": {
    "has_match": true,
    "confirmed": true,
    "match_confidence": 0.92,
    "relationship": "entity",
    "source": "Local KYC sanctions flags",
    "evidence_id": "SAN-828"
  },
  "transactions": {
    "suspicious_probability": 0.76,
    "monthly_volume_change": 2.0,
    "high_risk_country_transfers": 4,
    "typology_hits": 2,
    "evidence_id": "TXN-828"
  },
  "adverse_media": {
    "negative_news_found": true,
    "severity": "HIGH",
    "source": "Sectoral sanctions signal",
    "source_count": 1,
    "confidence": 0.72,
    "mentions_sanctions": true,
    "evidence_id": "MEDIA-828"
  },
  "ownership": {
    "sanctioned_ubo": false,
    "shell_layers": 2,
    "tax_haven_link": false,
    "confidence": 0.75,
    "evidence_id": "OWN-828"
  },
  "fatf_high_risk": true
}
```

## Output Highlights

The engine returns:

```text
risk_score
base_score
risk_level
confidence_score
risk_delta
risk_trend
velocity
escalation_floor
applied_overrides
trigger_investigation
sar_recommended
breakdown
component_details with sub_factors
evidence_ids
top_reasons
timeline_event
model_version
```

Example explanation line:

```text
+16.6 pts: Direct entity sanctions match (92% confidence)
```

## FastAPI Routes

Start the app:

```bash
uvicorn risk_engine.api:app --reload
```

Open dashboard:

```text
http://127.0.0.1:8000/
```

API docs:

```text
http://127.0.0.1:8000/docs
```

Useful routes:

```text
GET  /health
POST /risk/assess
GET  /governance/summary
GET  /governance/cases
GET  /governance/cases/{customer_id}
GET  /governance/cases/{customer_id}/live-news
POST /governance/cases/{customer_id}/review
POST /governance/cases/{customer_id}/sar-signoff
GET  /governance/audit
```

## Live News API

Live adverse-media lookup uses NewsAPI only when `NEWS_API_KEY` is set.

In Git Bash:

```bash
export NEWS_API_KEY="your_key_here"
uvicorn risk_engine.api:app --reload
```

In PowerShell:

```powershell
$env:NEWS_API_KEY="your_key_here"
uvicorn risk_engine.api:app --reload
```

Do not hardcode or commit the real API key.

## Test Commands

Run all tests:

```bash
python -m unittest discover -s tests
```

Run demo assessment:

```bash
python examples/demo_risk_engine.py
```

Test API health:

```bash
curl http://127.0.0.1:8000/health
```

Test dataset-backed summary:

```bash
curl http://127.0.0.1:8000/governance/summary
```

## Team Integration Notes

Secure Data / Identity team:
- Provide KYC profile fields and previous score history.
- Respect RBAC masking for sensitive fields.

Entity Intelligence team:
- Provide sanctions/entity-resolution match confidence.
- Provide ownership/UBO signals and evidence IDs.

Risk Intelligence team:
- Own `risk_engine/engine.py`, `scoring.py`, `config.py`, and dataset-to-risk mapping.
- Keep risk and confidence separate.

Agent / Orchestration team:
- Use `trigger_investigation` to start investigation.
- Use `sar_recommended` to request report/SAR drafting.
- Do not let agents directly mutate risk scores.

Frontend / Governance team:
- Display `breakdown`, `sub_factors`, `top_reasons`, `velocity`, and audit trail.
- Ensure every human decision requires a typed reason.

Audit team:
- Persist `timeline_event`, `model_version`, `evidence_ids`, and `applied_overrides`.
- Current governance layer already has hash-chained audit entries.

## Current Verified State

Last verified command:

```bash
python -m unittest discover -s tests
```

Expected result:

```text
Ran 9 tests
OK
```