# KYC Ingestion & Normalization (Phase 2)

Secure, deterministic pipeline that turns a raw KYC dataset file into validated
`NormalizedKYCEntity` records plus a PII-safe data-quality report.

```
raw file -> file validation -> CSV read -> source-schema check
        -> row normalization -> duplicate detection -> NormalizedKYCEntity[]
        -> DataQualityReport
```

## Ingestion channels (CSV / XLSX / API)

All three channels converge on ONE shared normalization core
(`normalize_batch` in `pipelines/kyc_ingestion_pipeline.py`) → identical
validation, duplicate handling, reporting, and the same `NormalizedKYCEntity`
contract:

```
CSV connector   ─┐
XLSX connector  ─┼─► normalize_batch(header, rows) ─► NormalizedKYCEntity[] + DataQualityReport
API connector   ─┘
```

- **CSV**: implemented (stdlib `csv`). **XLSX**: implemented in Phase 10
  (`read_xlsx_rows`, `openpyxl` read-only + data-only — see §XLSX below) —
  it feeds the **same** `normalize_batch`, so validation, dedup, reporting,
  PII handling, and audit events are identical to CSV. The real challenge
  dataset is CSV; XLSX exists so the deliverable's stated channel is real and
  tested, not just planned.
- **API** (Phase 5): secure OUTBOUND client pulling from trusted configured
  sources, then mapping source→canonical fields into the same `normalize_batch`.
  See **docs/api-ingestion.md** (SSRF defenses, trusted-source registry, secret
  boundary, RBAC-protected trigger). API data is untrusted and gets the *same*
  schema/PII validation as files.

Modules (under `backend/app/ingestion/`): `connectors/kyc_file_connector.py`,
`validators/file_validator.py`, `validators/kyc_schema_validator.py`,
`mapping.py`, `pipelines/kyc_ingestion_pipeline.py`, `reports.py`, `errors.py`,
`jobs/inspect_kyc_dataset.py`, `jobs/run_kyc_ingestion.py`.

## 1. Actual source dataset

- **File:** `clients_with_fatf_ofac.csv` — CSV, UTF-8, ~138 KB, **2000 rows**,
  12 columns, comma-delimited, no nulls, no duplicate `client_id`.
- The sibling `transactions_with_fatf_ofac.csv` (~2.9 MB) belongs to the
  **risk-intelligence** teammate and is **out of scope** here.

### Actual source columns

`client_id, client_name, client_type, sector, sector_risk, country, pep_flag,
sanctions_flag, fatf_country_flag, ofac_country_flag, sectoral_sanctions_flag,
ownership_opacity_score`

Observed value shapes: `client_id` numeric unique string; `client_type` ∈ {NGO,
Financial Institution, Corporate, Individual}; `sector_risk` ∈ {High, Medium,
Low}; boolean flags ∈ {0,1}; `country` ISO-2 (21 distinct);
`ownership_opacity_score` float 0.0–1.0.

## 2. Source-to-canonical mapping

Defined centrally in `ingestion/mapping.py` (`COLUMN_MAP`). The dataset already
uses canonical snake_case names, so the map is mostly identity:

| Source column | Canonical field |
|---|---|
| `client_id` | `client_id` |
| `client_name` | `client_name` |
| `client_type` | `client_type` |
| `country` | `country` |
| `sector` | `sector` |
| `sector_risk` | `sector_risk` (→ enum) |
| `pep_flag` | `pep_flag` (→ bool) |
| `sanctions_flag` | `sanctions_flag` (→ bool) |
| `fatf_country_flag` | `fatf_country_flag` (→ bool) |

**Additional source columns** (`ofac_country_flag`, `sectoral_sanctions_flag`,
`ownership_opacity_score`) are recognized and reported as
`additional_source_columns` but are **not** part of the canonical contract yet —
they are candidates for a future coordinated contract extension (likely
relevant to entity-intelligence / risk workstreams).

## 3. Supported file types

**`.csv`** (stdlib `csv`) and **`.xlsx`** (`openpyxl`, Phase 10). Both feed
the same `normalize_batch`. `read_kyc_rows(path)` dispatches by the
already-validated extension. `.xlsm` (macro-enabled), archives, and
executables are never supported (`SUPPORTED_EXTENSIONS = {".csv", ".xlsx"}`).

### XLSX safety posture

- Opened `openpyxl.load_workbook(path, read_only=True, data_only=True)`:
  streaming (memory-bounded) and **cached values only** — formula *text* is
  never returned, and openpyxl is not a calculation engine, so **no formula
  is ever evaluated**.
- Only the **first worksheet** is read; additional sheets are ignored, never
  silently merged.
- Every cell is coerced to a **string** (matching CSV all-strings semantics)
  before it reaches the shared normalizer.
- A corrupt / non-spreadsheet `.xlsx` (including a CSV renamed to `.xlsx`)
  raises `CorruptFileError` — the underlying parser error is chained but not
  surfaced in the message (no library internals leaked).
- Row count is capped (`MAX_XLSX_ROWS = 1_000_000`) as decompression/row-bomb
  defense-in-depth, on top of the compressed-size limit enforced by
  `validate_kyc_file`. A pathological zip-bomb `.xlsx` is a documented
  residual limitation (§Limitations) — production would add AV/content-disarm
  at the file boundary.
- No spreadsheet output is ever written by this system, so CSV/formula
  **injection on export** is not applicable.

## 4. Approved input directory

Files are ingested **only** when they resolve inside the configured KYC dir
(`settings.kyc_raw_dir`, default `data/raw/kyc/`, anchored at the repo root).
Absolute paths, `..` traversal, and symlink escapes are rejected
(`KycPathError`). The real dataset was copied into `data/raw/kyc/` for local
verification; the original under `data/raw/kyc_profiles/` is left untouched.
Both are git-ignored.

## 5. File-size limit

Configurable via `MAX_KYC_FILE_SIZE_MB` (default **50 MB**; dataset is ~138 KB).
Enforced once, in `file_validator.py`; injectable in tests.

## 6. Normalization rules (deterministic, conservative)

| Field | Rule |
|---|---|
| `client_id` | strip; reject blank/missing; never invented; max 64 chars |
| `client_name` | trim + collapse internal whitespace; preserve punctuation; reject blank; max 256 |
| `client_type` | trim + collapse whitespace; max 64 |
| `country` | trim + collapse whitespace + **upper-case**; reject blank; max 64 |
| `sector` | trim + collapse whitespace; reject blank; max 128 |
| `sector_risk` | map category → enum (see §8) |
| boolean flags | safe token map (see §7) |
| `aliases` | source has none → safe empty-list default (never invented) |
| `created_at`/`updated_at` | set to ingestion time; **record** timestamps, not source/customer dates |

Nothing is silently corrected: every rejection or coercion failure becomes a
traceable `ValidationIssue`.

## 7. Boolean normalization

Case-insensitive map (`ingestion/mapping.normalize_bool`):
`true/1/yes/y/t → True`, `false/0/no/n/f → False`. **`bool("false")` is never
used** (it returns `True`). Unknown tokens are **not** coerced — they raise and
the row gets an `invalid_boolean` issue and is not emitted.

## 8. Sector-risk normalization

Source is categorical (`High/Medium/Low`), so the canonical `sector_risk` is an
ordinal enum `SectorRiskLevel {low, medium, high}` — **not** a 0–100 number
(mapping to numbers would invent false precision). This is a documented Phase 2
change to `NormalizedKYCEntity` (see docs/integration-contracts.md). Unknown
categories → `invalid_sector_risk` issue.

## 9. Duplicate handling

`client_id` is canonical. Duplicates are detected across all rows. Policy: **no
silent winner** — every occurrence of a duplicated `client_id` is flagged
(`duplicate_client_id`) and **none** of those rows are emitted. The count of
duplicated values is reported as `duplicate_client_ids`.

## 10. Validation issues (PII-safe)

`ValidationIssue` = `{row_number, field, issue_code, message, client_ref}`. It
**never** contains the full raw row or raw customer names; `client_ref` is a
masked `client_id`. Issue codes: `missing_required_field`, `invalid_boolean`,
`invalid_sector_risk`, `duplicate_client_id`, `value_too_long`.

## 11. PII-safe logging / output

The pipeline prints only aggregates (counts, columns, masked ids). Raw names and
raw rows are never printed or logged. Secrets/JWTs/credentials are never logged.
The inspection job shows PII columns only as length ranges.

## 12. Formula-injection / untrusted content

Input files are untrusted. CSV values are read as plain strings and **never
evaluated**. XLSX (Phase 10) is read with openpyxl `data_only=True` in
read-only mode: cached cell values only, formula text is never returned, and
openpyxl never executes formulas. Cells starting with `= + - @` are therefore
just data strings here; because this system never writes spreadsheet/CSV
output, formula **injection on export** is not applicable. Enterprise
malware/AV scanning, content-disarm, and decompression-bomb limits beyond the
row cap would run in `file_validator` before parsing — **out of scope** for
this hackathon phase, noted as a production control.

## 13–15. Running it

From `backend/` (uses the approved KYC dir):

```bash
# Inspect (read-only, PII-safe schema + quality stats)
python -m app.ingestion.jobs.inspect_kyc_dataset [FILENAME]

# Run ingestion (concise PII-safe summary; optional dev artifact)
python -m app.ingestion.jobs.run_kyc_ingestion [FILENAME] [--write-jsonl]

# Tests (no network / DB / real-dataset dependency)
python -m pytest
```

`--write-jsonl` writes normalized records to `data/processed/…jsonl`
**in plaintext** (git-ignored, explicit opt-in, never on import) — a
convenience for local development/debugging only.

**For persisting sensitive normalized output, prefer the AES-256-GCM encrypted
path instead** (Phase 6):
`app.ingestion.pipelines.kyc_ingestion_pipeline.export_encrypted_kyc_artifact()`
writes an encrypted envelope to `data/encrypted/` via `EncryptedArtifactStore`
— no plaintext ever touches disk. See docs/encryption-at-rest.md.

### Real-dataset result (2000 rows)

`valid_rows=2000, invalid_rows=0, duplicate_client_ids=0`, no missing required
fields, no validation issues; `additional_source_columns =
[ofac_country_flag, sectoral_sanctions_flag, ownership_opacity_score]`.

## 16. Known limitations

- CSV whole file read into memory (fine at ~2k rows); XLSX is streamed
  (`read_only=True`) with a `MAX_XLSX_ROWS` cap. A pathological zip-bomb
  `.xlsx` (small compressed, huge decompressed) is only partially mitigated by
  the row cap + compressed-size limit — production needs AV/content-disarm.
- No malware/AV scanning (production control, documented above).
- The 3 extra sanctions/opacity columns are dropped from the canonical output
  pending a coordinated contract decision.
- No persistence/API (deliberate — later phases); output is in-memory + optional
  local JSONL.
- Duplicate policy rejects *all* occurrences; a survivorship/merge strategy is a
  future enhancement.
