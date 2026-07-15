# Data

**No real customer data belongs in this repository, at any stage.**

## Structure

- `raw/kyc_profiles/`, `raw/aml_transactions/`, `raw/sanctions/`, `raw/regulatory/` — local-only landing zones for raw source data during development. Git-ignored; only `.gitkeep` is tracked.
- `processed/` — local-only landing zone for processed data. Git-ignored; only `.gitkeep` is tracked.
- `samples/` — small, synthetic, clearly-fake sample datasets that contain no real PII. These may be committed if explicitly reviewed and whitelisted (see root `.gitignore`).

## Rules

1. Never commit raw KYC data.
2. Never commit the AML transaction dataset (500 MB-1 GB class).
3. Never commit downloaded OpenSanctions/OFAC datasets unless explicitly approved and size-safe.
4. Only `.gitkeep` files and reviewed synthetic samples under `samples/` may be tracked.
