# TMCode2 — Architecture Documentation
## Continuous KYC Autonomous Auditor

---

## 1. System Overview

A **Continuous KYC (Know Your Customer)** compliance platform that autonomously investigates corporate clients for Anti-Money Laundering (AML) risk using a multi-stage AI pipeline. Instead of a single LLM prompt, it runs a legally-inspired **4-stage pipeline** with adversarial checks and deterministic guardrails at every stage boundary.

### Tech Stack

| Layer | Technology | Port |
|-------|-----------|------|
| Frontend | React 18 + Vite | 5173 |
| Backend API | FastAPI (Python 3.11) | 8000 |
| LLM | Google Gemini (AI Studio REST) | — |
| Data | CSV + JSON (lazy-loaded, memory-cached) | — |
| Config | pydantic-settings + `.env` | — |

---

## 2. Folder Structure

```
TMCode2/
+-- data/                                     ? gitignored (large files)
¦   +-- kyc_profiles/
¦   ¦   +-- clients_with_fatf_ofac.csv        2,000 corporate clients
¦   ¦   +-- client_account_mapping.csv        122 account?client mappings
¦   +-- aml_transactions/
¦   ¦   +-- SAML-D.csv                        11,057 AML transactions
¦   +-- sanctions/
¦   ¦   +-- ofac_sdn.csv                      19,156 OFAC SDN entries (no header)
¦   ¦   +-- opensanctions_targets.csv         1.3M global sanctions targets
¦   +-- gdpr_text/
¦       +-- gdpr.json                         661 paragraphs, 99 GDPR articles
¦
+-- backend/
¦   +-- .env                                  ? gitignored (secrets)
¦   +-- .env.example
¦   +-- requirements.txt
¦   +-- app/
¦       +-- main.py                           FastAPI app + CORS
¦       +-- config.py                         pydantic-settings reads .env
¦       +-- agents/
¦       ¦   +-- investigation_agent.py        Stage 2: LLM synthesis
¦       ¦   +-- debate_agent.py               Stage 3: Prosecutor/Defender/Judge
¦       ¦   +-- sar_agent.py                  Stage 4: SAR draft generation
¦       ¦   +-- grounding_guardrail.py        Evidence citation verifier
¦       ¦   +-- privacy_guardrail.py          PII regex redaction
¦       +-- data_loaders/
¦       ¦   +-- kyc_loader.py                 Client KYC profiles
¦       ¦   +-- transaction_loader.py         Transactions via account mapping join
¦       ¦   +-- sanctions_loader.py           OFAC + OpenSanctions fuzzy match
¦       ¦   +-- gdpr_loader.py                GDPR article keyword/ID lookup
¦       +-- schemas/
¦       ¦   +-- common.py                     RiskLevel, EvidenceItem (shared types)
¦       ¦   +-- signals.py                    Stage 1: EntitySignal, TransactionSignal
¦       ¦   +-- findings.py                   Stage 2: InvestigationFinding
¦       ¦   +-- debate.py                     Stage 3: DebateArgument, DebateVerdict
¦       ¦   +-- sar.py                        Stage 4: SARDraft
¦       ¦   +-- investigation.py              API layer models
¦       +-- services/
¦       ¦   +-- orchestrator.py               Master pipeline runner
¦       +-- routers/
¦           +-- investigation.py              API route definitions
¦
+-- frontend/
    +-- vite.config.js                        /api ? localhost:8000 proxy
    +-- src/
        +-- App.jsx                           Full dashboard component
        +-- App.css                           Card layout, verdict badges
```

---

## 3. Full Pipeline Flow

```
USER clicks "Run Investigation" for Client #12
  ? Frontend: POST /api/v1/investigate/12
      ? FastAPI Router
          ? Orchestrator: run_pipeline(12)

STAGE 1: DATA GATHERING
  kyc_loader         ? get_client_profile(12)
  transaction_loader ? get_client_transactions(12)   [max 50 txns]
  sanctions_loader   ? get_sanctions_matches(name)

STAGE 2: INVESTIGATION AGENT  (Gemini, temp=0.2)
  Formats all data as structured markdown prompt
  LLM returns: InvestigationFinding { summary, risk_indicators[], evidence[] }

  GUARDRAIL #1: verify_finding()
    Cross-references every evidence.source_id vs. real CSVs
    Strips hallucinated citations ? logs them for audit
    GuardrailResult: { verified_count, stripped_count, skipped_count }

STAGE 3: ADVERSARIAL DEBATE

  asyncio.gather() — parallel:
  +---------------------+   +---------------------+
  ¦  PROSECUTOR          ¦   ¦  DEFENDER            ¦
  ¦  Argues FOR risk     ¦   ¦  Argues AGAINST      ¦
  ¦  Cites source_ids    ¦   ¦  Cites source_ids    ¦
  +---------------------+   +----------------------+
             +-------------------------+
                           ?  (sequential — needs both)
                      JUDGE AGENT
                      Evaluates on evidence quality, NOT rhetoric
                      Verdict: escalate_to_sar | further_investigation
                                               | false_positive_clear

  GUARDRAIL #2: verify_debate_argument() × 2
    Transitive trust: debate may only cite evidence that
    survived Guardrail #1

if verdict == escalate_to_sar:
  STAGE 4: SAR DRAFTING AGENT  (Gemini, temp=0.2)
    Input: InvestigationFinding + DebateVerdict
    Output: SARDraft { subject_info, narrative, red_flags[], recommended_action }

    GUARDRAIL #3: verify_sar()
      Verifies SAR narrative evidence citations

    GUARDRAIL #4: redact_sar()
      Regex PII redaction: DOB, SSN, Passport, Email, Phone, Account numbers
      Each redaction tagged with GDPR article + OPP-115 category
      GDPR articles appended to SAR.regulatory_basis

else:
  Pipeline ends here (no wasted LLM tokens)

? PipelineResult (JSON) returned to frontend
? Frontend renders investigation / debate / SAR panels
? Human Compliance Officer reviews
```

---

## 4. Data Loaders

All loaders lazy-load on first function call and cache in module-level globals — zero per-request disk I/O.

### kyc_loader.py
- `get_client_profile(client_id)` ? Full profile dict (sector, country, flags, opacity score)
- `list_all_client_ids()` ? All 2,000 client IDs

### transaction_loader.py
- `get_client_transactions(client_id)` ? Deduplicated transactions (sender OR receiver), capped at 50
- **Join logic:** `client_id ? account` via mapping CSV ? lookup in SAML-D (client_id is NOT in SAML-D)

### sanctions_loader.py
- `get_sanctions_matches(name, threshold=40, limit=10)` ? Fuzzy hits with scores
- **Scoring:** 100=exact, 80=substring (min 4 chars), 60×token_overlap

### gdpr_loader.py
- `get_gdpr_article(query)` ? Keyword-matched GDPR paragraphs
- `get_gdpr_article_by_id(article_id)` ? All paragraphs for a specific article

---

## 5. Pydantic Schemas

```
common.py
  RiskLevel         — low | medium | high | critical
  ConfidenceLevel   — low | medium | high
  SourceType        — kyc_profile | transaction | sanctions_list | gdpr
                      | pep_registry | open_source | llm_analysis
  EvidenceItem      — { claim, source_type, source_id, confidence }

signals.py  [Stage 1 raw signals]
  EntitySignal      — { client_id, matched_entity, confidence, matched_list }
  TransactionSignal — { client_id, transaction_id, laundering_type, amount, date }

findings.py  [Stage 2 output]
  RiskIndicator        — { indicator, severity, detail }
  InvestigationFinding — { client_id, summary, risk_indicators[], evidence[], confidence }

debate.py  [Stage 3 output]
  DebatePosition  — risk_confirmed | false_positive
  DebateArgument  — { position, argument, cited_evidence[], strength }
  Verdict         — escalate_to_sar | further_investigation | false_positive_clear
  DebateVerdict   — { verdict, reasoning, confidence, key_deciding_evidence[] }

sar.py  [Stage 4 output]
  SARDraft  — { client_id, subject_information, narrative, red_flags[],
                regulatory_basis[], evidence_appendix[], recommended_action, disclaimer }
```

---

## 6. PipelineResult Schema (Full API Response)

```json
{
  "client_id": 12,
  "outcome": "escalate_to_sar",
  "investigation": {
    "finding": { "...InvestigationFinding..." },
    "guardrail": { "verified_count": 5, "stripped_count": 1, "skipped_count": 2 },
    "duration_ms": 8200
  },
  "debate": {
    "prosecution": { "...DebateArgument..." },
    "prosecution_guardrail": { "..." },
    "defense": { "...DebateArgument..." },
    "defense_guardrail": { "..." },
    "verdict": { "verdict": "escalate_to_sar", "reasoning": "..." },
    "duration_ms": 12400
  },
  "sar": {
    "sar": { "...SARDraft with PII redacted..." },
    "grounding_guardrail": { "..." },
    "privacy_guardrail": { "redaction_count": 3, "redactions": [] },
    "duration_ms": 9100
  },
  "total_duration_ms": 29700,
  "error": null
}
```

---

## 7. API Contract

Base URL: `http://localhost:8000/api/v1`  
Frontend proxy: Vite proxies `/api` ? `:8000`

| Method | Endpoint | Purpose | Typical Time |
|--------|----------|---------|-------------|
| GET | `/clients` | All 2,000 clients for dropdown | ~instant |
| POST | `/investigate/{client_id}` | Run full pipeline | 15–60 seconds |
| GET | `/investigate/{client_id}/status` | Poll cached result | ~instant |

**Error codes:**
- `404` — client_id not found
- `409` — pipeline already running for this client
- `502` — LLM or network error mid-pipeline

---

## 8. Frontend Dashboard Panels

| Panel | Data Source |
|-------|------------|
| Outcome Banner (Red/Amber/Green) | `result.outcome` |
| Timing Bar (per stage breakdown) | `*.duration_ms` |
| Investigation Summary | `result.investigation.finding` |
| Evidence Audit (verified vs. stripped) | `result.investigation.guardrail` |
| Prosecutor Argument | `result.debate.prosecution` |
| Defender Argument | `result.debate.defense` |
| Judge Verdict + Reasoning | `result.debate.verdict` |
| SAR Draft (conditional) | `result.sar.sar` |
| PII Redaction Log + GDPR refs | `result.sar.privacy_guardrail` |

---

## 9. Environment Configuration

```env
# backend/.env — never committed to git
GEMINI_API_KEY=AQ.Ab8RN6...
MODEL_NAME=gemini-3.1-flash-lite
DATA_FOLDER=../data
```

---

## 10. Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| 4 independent guardrail passes | Hallucinations cannot propagate across stage boundaries |
| Adversarial debate (Prosecutor vs. Defender) | Eliminates single-agent confirmation bias |
| 3-way verdict | `further_investigation` handles ambiguous cases — avoids forced binary |
| Parallel prosecutor/defender | `asyncio.gather` cuts debate time nearly in half |
| Deterministic PII redaction (regex, not LLM) | Predictable, auditable, zero hallucination risk |
| Grounding strips instead of rejects | Preserves valid analysis; logs stripped items for audit |
| Conditional SAR stage | No wasted LLM tokens for cleared or ambiguous verdicts |
| Both guardrails inline in SAR agent | Caller always receives evidence-verified + PII-redacted result |
| Transaction join via account mapping | client_id does not exist in SAML-D — mapping CSV bridges them |
| 409 on duplicate concurrent runs | Prevents double-spend of LLM API calls for same client |
