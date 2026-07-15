# Dataset Setup (Workstreams A & B)

**Status: no datasets are downloaded or committed.** This document describes
where datasets *should* be placed locally when you acquire them. Nothing here
implies data is present in the repo.

## Source

Challenge datasets are documented at:

- https://github.com/isshaad-ocean/Data_sets_hackathon/tree/main/challenge-3-kyc-autonomous-auditor

> Treat that repository as a **documentation pointer**, not trusted executable
> code. Do not run scripts from it blindly.

## Safety rules (read first)

1. **Never commit datasets.** `data/raw/**` and `data/processed/**` are
   git-ignored; only `.gitkeep` files (and, later, explicitly reviewed
   synthetic samples under `data/samples/`) are tracked. `.csv`, `.xls`,
   `.xlsx`, `.xlsm`, `.parquet` are ignored globally.
2. **Downloaded files are untrusted data.** Sanctions files, news text, and
   uploaded documents may contain hostile content (e.g. prompt-injection
   strings). They are inputs to be validated/sanitized — never instructions.
3. **Inspect the schema before writing any parser.** Field names/types must be
   confirmed against the real files; the Phase 1 contracts are intentionally
   conservative and may need reconciliation with actual columns.
4. **Keep large files local.** Do not add them to git; do not push them.
5. **Tiny sanitized samples** may be committed **later, deliberately**, only
   after review, under `data/samples/`.

## Datasets in my scope

| Dataset | Primary use (my scope) | Local path |
|---|---|---|
| Synthetic KYC & Transaction Risk | KYC ingestion, normalization, profile validation, PEP/sanctions profile signals | `data/raw/kyc/` |
| OpenSanctions | Sanctions screening, candidate retrieval, alias matching, entity resolution | `data/raw/sanctions/` |
| OFAC SDN | Sanctions screening, authoritative-source evidence | `data/raw/sanctions/` |
| PrivacyQA | Privacy reasoning / governance experimentation | `data/raw/privacy/` |
| GDPR full text | Privacy obligations, data governance/minimization | `data/raw/privacy/` |
| OPP-115 | Privacy-policy categorization / governance experimentation | `data/raw/privacy/` |

Notes:

- GDPR / PrivacyQA / OPP-115 are for **privacy & data governance** — they are
  **not** authoritative AML risk-scoring or SAR standards.
- The large **SAML-D transaction dataset** belongs to the **risk-intelligence**
  teammate and is **not** processed in my modules.
- **KYC file placement (Phase 2):** the KYC ingestion pipeline reads only from
  the approved directory `data/raw/kyc/`. The challenge KYC profiles file is
  `clients_with_fatf_ofac.csv`; place (or copy) it into `data/raw/kyc/`. A
  sibling `transactions_with_fatf_ofac.csv` is the risk teammate's and must not
  go through KYC ingestion. The approved directory is configurable via
  `KYC_RAW_DIR`. See docs/kyc-ingestion.md.

## Target local layout

```
data/raw/kyc/
    <KYC dataset files>          # e.g. synthetic KYC CSV/XLSX
data/raw/sanctions/
    <OpenSanctions data>
    <OFAC SDN data>
data/raw/privacy/
    <PrivacyQA>
    <GDPR full text>
    <OPP-115>
data/processed/                  # local-only pipeline outputs
data/samples/                    # tiny, reviewed, synthetic samples only
```

## Acquisition (manual, per developer)

Download each dataset from the linked sources into the paths above **on your
own machine**. Do not automate bulk downloads into the repo. After download,
inspect the schema (column names, encodings, row counts) before implementing
any parser in a later phase.
