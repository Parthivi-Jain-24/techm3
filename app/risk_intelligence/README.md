# Risk Intelligence

**Owner:** Workstream 3 (AML Transaction Monitoring, ML Models, Risk Scoring, Confidence Scoring, Risk Timeline)

## Purpose

Monitor transaction risk and AML patterns, and maintain a continuous, explainable customer risk score and risk timeline.

## Structure

- `transaction_monitoring/` — AML pattern detection over transaction data.
- `feature_engineering/` — feature pipelines feeding ML models.
- `models/` — model wrappers/interfaces (trained artifacts live in `ml/artifacts/`, never committed here).
- `scoring/` — risk score computation.
- `confidence/` — confidence scoring for risk outputs.
- `timeline/` — historical risk timeline construction per client.

## Inputs

Normalized transaction data from `ingestion/`, `Entity Intelligence Result` records from `entity_intelligence/` (Workstream 2).

## Outputs

`Risk Assessment` records (score, level, confidence, factors, evidence references) consumed by `agents/` (Workstream 4).

## Public Interface Expectations

Risk outputs must be explainable — always include `risk_factors` and `evidence_ids`, never a bare numeric score.

## Security Considerations

- Model artifacts and training data are never committed to Git (see `.gitignore`).
- No real transaction data in this repository — synthetic samples only, under `data/samples/`.

## Integration Dependencies

- `ml/` for model training/evaluation (separate from runtime scoring code here).
- `backend/app/evidence/` for evidence linkage.
