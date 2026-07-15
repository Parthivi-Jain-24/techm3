# ML

**Owner:** Workstream 3 (AML Transaction Monitoring, ML Models, Risk Scoring, Confidence Scoring, Risk Timeline)

## Purpose

Model training, evaluation, and experimentation for AML pattern detection and risk scoring. Runtime scoring code lives in `backend/app/risk_intelligence/`; this directory is for offline training/evaluation work.

## Structure

- `notebooks/` — exploratory analysis and prototyping notebooks.
- `training/` — training scripts/pipelines.
- `evaluation/` — model evaluation scripts and metrics.
- `artifacts/` — trained model artifacts (git-ignored; never commit real weights/binaries here).
- `experiments/` — experiment tracking/config.

## Security Considerations

- No real AML/transaction datasets in this repository. Use synthetic data under `data/samples/` for local development.
- Trained model artifacts are git-ignored (`ml/artifacts/*`) — manage them via an external artifact store when the project matures.
- Do not commit notebook outputs containing real data.
