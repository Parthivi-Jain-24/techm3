# TMCode2 — Agents Documentation
## All AI Agents & Guardrails

---

## Overview

The pipeline has **3 LLM agents** and **2 guardrails** that run in sequence. Each agent calls Google Gemini via the AI Studio REST API. Guardrails are deterministic (no LLM) and run between every agent stage.

```
investigate()          ? LLM Agent
    ?
verify_finding()       ? Grounding Guardrail
    ?
run_debate()           ? LLM Agent (3 internal calls)
    ?
verify_debate_argument() × 2  ? Grounding Guardrail
    ?
draft_sar()  [conditional]    ? LLM Agent
    ?
verify_sar()           ? Grounding Guardrail
    ?
redact_sar()           ? Privacy Guardrail
```

---

## Agent 1 — Investigation Agent

**File:** `backend/app/agents/investigation_agent.py`  
**Stage:** 2 of 4  
**Signature:** `async def investigate(client_id: int) ? InvestigationFinding`

### Role
Takes a `client_id`, gathers all available data via the data loaders, sends it to Gemini, and returns a validated `InvestigationFinding` with every claim cited to a real source.

### Data it receives (from loaders)
| Data | Loader Call | Context Block in Prompt |
|------|------------|------------------------|
| KYC profile | `get_client_profile(client_id)` | `## Client Profile` JSON block |
| Transactions | `get_client_transactions(client_id)` | `## Transactions` — capped at 50 |
| Sanctions hits | `get_sanctions_matches(client_name)` | `## Sanctions Screening Matches` |

### LLM Settings
| Setting | Value |
|---------|-------|
| Model | `gemini-3.1-flash-lite` (from `MODEL_NAME` env var) |
| Temperature | `0.2` (low — deterministic compliance output) |
| Output format | `responseMimeType: application/json` |
| Timeout | 120 seconds |
| Retries | Up to 3× with 10/20/30s backoff on 429 or 503 |

### Prompt Rules (enforced via system prompt)
1. Every claim **must** reference a real `source_id` (transaction ID, sanctions record, profile field)
2. Label facts vs. inferences explicitly
3. Evaluate sanctions name matches using DOB/nationality/aliases to reduce false positives
4. Detect cross-transaction **patterns** (structuring, timing clusters) — not just per-transaction flags
5. Output strict JSON only — no prose outside the JSON block
6. Transaction prompt is capped at 50 rows; the LLM is told the total count so it knows if data was truncated

### Output Schema
```python
InvestigationFinding {
    client_id: int                     # forced server-side after parse
    summary: str                       # plain-English synopsis
    risk_indicators: [RiskIndicator]   # { indicator, severity: RiskLevel, detail }
    evidence: [EvidenceItem]           # { claim, source_type, source_id, confidence }
    confidence: ConfidenceLevel        # low | medium | high
}
```

### Guardrail Note
After the agent returns, `verify_finding()` strips any `evidence` items whose `source_id` cannot be resolved to real CSV data. The agent cannot know what will be stripped — it must cite honestly.

---

## Agent 2 — Debate Agent

**File:** `backend/app/agents/debate_agent.py`  
**Stage:** 3 of 4  
**Signature:** `async def run_debate(finding: InvestigationFinding) ? DebateResult`

### Role
Runs an adversarial cross-check via three separate LLM calls. Forces one agent to argue FOR risk and another AGAINST — then a judge evaluates both on evidence quality alone.

### Why Adversarial?
A single agent assessing risk has confirmation bias — it tends to validate its own initial assessment. Forcing explicit opposing positions surfaces weaknesses in the evidence that a single analysis would gloss over.

### Execution Flow
```
InvestigationFinding
        ¦
   asyncio.gather()   ? parallel (no data dependency between them)
   +---------+
   ?         ?
PROSECUTOR  DEFENDER
   +---------+
        ?          ? sequential (judge needs both arguments)
      JUDGE
        ¦
   DebateResult
```

### Sub-Agent 2a — Prosecutor
| Setting | Value |
|---------|-------|
| Role | Argue the client is a genuine compliance risk |
| Position | `risk_confirmed` (forced server-side after parse) |
| Temperature | `0.3` |
| Prompt rule | Must cite `source_id` values — no rhetorical appeals |

### Sub-Agent 2b — Defender
| Setting | Value |
|---------|-------|
| Role | Argue the client is a false positive |
| Position | `false_positive` (forced server-side after parse) |
| Temperature | `0.3` |
| Prompt rule | Rule 3: "Do not dismiss real red flags dishonestly" — prevents reflexive false-clearing |

### Sub-Agent 2c — Judge
| Setting | Value |
|---------|-------|
| Role | Evaluate both arguments and issue a binding verdict |
| Input | InvestigationFinding + Prosecution argument + Defense argument |
| Temperature | `0.3` |
| Prompt rule 1 | Evaluate strictly on **evidence cited**, not rhetorical strength |
| Prompt rule 2 | The more eloquent agent cannot win on style alone |

### Output Schemas
```python
DebateArgument {
    position: DebatePosition        # risk_confirmed | false_positive
    argument: str                   # substantive claim with evidence citations
    cited_evidence: [str]           # source_id references from InvestigationFinding
    strength: ConfidenceLevel
}

DebateVerdict {
    verdict: Verdict                # escalate_to_sar | further_investigation | false_positive_clear
    reasoning: str                  # step-by-step explanation
    confidence: ConfidenceLevel
    key_deciding_evidence: [str]    # source_ids that most influenced the ruling
}

DebateResult {
    finding: InvestigationFinding   # passed through for downstream use
    prosecution: DebateArgument
    defense: DebateArgument
    verdict: DebateVerdict
}
```

### 3-Way Verdict Design
| Verdict | Meaning | What Happens Next |
|---------|---------|------------------|
| `escalate_to_sar` | Genuine compliance risk — file a SAR | Stage 4 (SAR drafting) runs |
| `further_investigation` | Ambiguous — more data needed | Pipeline returns debate output, stops |
| `false_positive_clear` | Client cleared | Pipeline stops immediately — no wasted LLM call |

---

## Agent 3 — SAR Drafting Agent

**File:** `backend/app/agents/sar_agent.py`  
**Stage:** 4 of 4 (conditional — only when verdict is `escalate_to_sar`)  
**Signature:** `async def draft_sar(finding: InvestigationFinding, verdict: DebateVerdict) ? SARResult`

### Role
Generates a FinCEN-style Suspicious Activity Report (SAR) draft, then runs both guardrails (grounding + privacy) internally before returning. The caller always receives a result that is guaranteed evidence-verified and PII-redacted.

### Execution Flow
```
InvestigationFinding + DebateVerdict
        ¦
        ?
   Gemini LLM call ? SARDraft (raw)
        ¦
        ?
   verify_sar()   ? Grounding Guardrail #3 (inline)
        ¦
        ?
   redact_sar()   ? Privacy Guardrail #4 (inline)
        ¦
        ?
   SARResult
```

### LLM Settings
| Setting | Value |
|---------|-------|
| Temperature | `0.2` (lowest — SAR language must be formal and reproducible) |
| Timeout | 120 seconds |

### Prompt Design
The LLM sees two JSON blocks as context:
1. **`## Investigation Finding`** — full verified InvestigationFinding (with all evidence source_ids)
2. **`## Debate Verdict`** — full DebateVerdict (verdict + reasoning + key deciding evidence)

This lets the SAR narrative address the **specific factors the judge found decisive**, not just generic risk language.

### Prompt Rules
1. Write in formal compliance language — factual, no dramatisation
2. Every narrative claim must cite a `source_id`
3. Do not re-introduce raw PII (privacy guardrail will catch anything that slips through)
4. Use generic AML obligation reference if no specific GDPR articles are available — do not invent statute citations
5. Hedge proportional to evidence confidence scores
6. Every draft must include a disclaimer marking it as AI-generated and requiring human sign-off

### Output Schema
```python
SARDraft {
    client_id: int                  # forced server-side
    subject_information: str        # structured: name, type, jurisdiction, accounts
    narrative: str                  # full SAR narrative text
    red_flags: [str]                # bullet-point red flags
    regulatory_basis: [str]         # applicable regulations (GDPR articles appended by privacy guardrail)
    evidence_appendix: [EvidenceItem]
    recommended_action: str         # "file SAR" | "enhanced monitoring" | "account freeze"
    disclaimer: str                 # "AI-generated, requires human review before filing"
}

SARResult {
    sar: SARDraft                        # final redacted SAR
    grounding: GuardrailResult           # evidence verification report
    privacy: PrivacyGuardrailResult      # PII redaction log
}
```

---

## Guardrail 1 & 2 — Grounding Guardrail

**File:** `backend/app/agents/grounding_guardrail.py`

### Role
Post-LLM validation that sits between every agent stage. Verifies that evidence `source_id` values actually resolve to real records in loaded datasets. Strips unverifiable claims and collects them in a structured audit log.

### Function Signatures
```python
verify_finding(finding: InvestigationFinding) ? tuple[InvestigationFinding, GuardrailResult]
verify_debate_argument(argument: DebateArgument, finding: InvestigationFinding) ? tuple[DebateArgument, GuardrailResult]
verify_sar(sar: SARDraft) ? tuple[SARDraft, GuardrailResult]
```

### GuardrailResult Schema
```python
GuardrailResult {
    verified_count: int         # citations that resolved to real data
    stripped_count: int         # citations removed (hallucinated or unresolvable)
    skipped_count: int          # citations with no ground truth (llm_analysis, etc.)
    unverified: [UnverifiedCitation]   # detail on each stripped citation

UnverifiedCitation {
    claim: str
    source_id: str
    source_type: str
    reason: str                 # why verification failed
}
```

### Verification Logic by Source Type
| source_type | Verified Against | Method |
|-------------|-----------------|--------|
| `kyc_profile` | Client profile dict | Checks if source_id contains a known field name (sector_risk, pep_flag, etc.) |
| `transaction` | SAML-D transaction index | Extracts 6+ digit account numbers; tries composite key `Date\|Time\|Sender\|Receiver` |
| `sanctions_list` | OFAC + OpenSanctions name index | Strips prefixes, exact or substring match (min 4 chars) |
| `gdpr` | gdpr.json article IDs | Extracts article number via regex, normalizes, checks gdpr_loader |
| `pep_registry` | — | Passed through (no dataset loaded) |
| `open_source` | — | Passed through (no dataset loaded) |
| `llm_analysis` | — | Passed through (inference, not a data claim) |

### Debate Argument Verification (Special Logic)
`verify_debate_argument` does NOT re-check raw CSVs. Instead, it cross-references `cited_evidence` against the `source_id` values that **survived `verify_finding()`** — creating a transitive chain of trust. Debate agents can only cite evidence that has already been verified against real data. Fuzzy substring matching handles minor formatting differences.

### Design: Strip, Don't Reject
Unverifiable citations are stripped from the finding/argument, but the rest of the analysis continues. Stripped items are logged so compliance officers can see what the LLM tried to claim but couldn't substantiate.

---

## Guardrail 4 — Privacy Guardrail

**File:** `backend/app/agents/privacy_guardrail.py`

### Role
Final pre-human-review pass. Strips unnecessary PII from `SARDraft` free-text fields using deterministic regex — no ML, no LLM call. Each redaction is tagged with a GDPR article justification (looked up from `gdpr.json`) and an OPP-115 privacy category.

### Function Signature
```python
redact_sar(sar: SARDraft) ? tuple[SARDraft, PrivacyGuardrailResult]
```

### PrivacyGuardrailResult Schema
```python
PrivacyGuardrailResult {
    redaction_count: int
    redactions: [RedactionAction]
    gdpr_articles_cited: [str]    # new GDPR refs added to SAR.regulatory_basis

RedactionAction {
    field: str                    # which SARDraft field was redacted
    original_snippet: str         # the text that was redacted (first 80 chars)
    replacement: str              # e.g. "[PASSPORT_REDACTED]"
    gdpr_article: str             # e.g. "GDPR article9"
    gdpr_justification: str       # article title from gdpr.json
    opp115_category: str          # OPP-115 sensitivity category
    description: str              # why this was redacted
}
```

### Redaction Rules (applied in priority order — specific first)
| Priority | Pattern | Replacement | GDPR Article | OPP-115 Category |
|----------|---------|-------------|-------------|------------------|
| 1 | Dates near birth-keywords ("dob", "born", etc. within 40 chars) | `[DOB_REDACTED]` | Article 5 | Data Retention |
| 2 | SSN (XXX-XX-XXXX) | `[NATIONAL_ID_REDACTED]` | Article 9 | Data Retention |
| 3 | Passport (1-2 uppercase letters + 6-9 digits) | `[PASSPORT_REDACTED]` | Article 9 | Data Retention |
| 4 | Email addresses | `[EMAIL_REDACTED]` | Article 5 | First Party Collection/Use |
| 5 | Phone numbers (requires + prefix) | `[PHONE_REDACTED]` | Article 5 | First Party Collection/Use |
| 6 | Account numbers (7+ digits) | `[ACCT_REDACTED]` | Article 5 | Third Party Sharing/Collection |

**Rule ordering is critical:** Passport must run before account number (to prevent the digit portion from being caught by the wrong rule). SSN before phone for the same reason.

**Implementation:** Single-pass right-to-left replacement preserves offset positions — eliminates the stale-text bug from dual-loop approaches.

### Fields Processed
| SARDraft Field | Treatment |
|----------------|-----------|
| `subject_information` | Full redaction pass (all 6 rules) |
| `narrative` | Full redaction pass |
| `red_flags` | Account numbers only (7+ digits) |
| `regulatory_basis` | GDPR refs appended (not redacted) |
| `recommended_action` | Not redacted (legally required) |
| `disclaimer` | Not redacted |
| `evidence_appendix` | Not redacted (structured data, handled by grounding guardrail) |

### DOB Context Guard
Date patterns appear in both birth dates AND SAR transaction timelines. The rule only redacts when a birth-related keyword ("born", "dob", "birth", "date of birth", "d.o.b") appears within 40 characters before the date. Transaction dates in the SAR narrative are preserved.

---

## Retry & Resilience Logic

All three LLM agents implement the same retry pattern:

```python
for attempt in range(4):
    resp = await client.post(url, json=payload, params=params)
    if resp.status_code in (429, 503) and attempt < 3:
        wait = (attempt + 1) * 10   # 10s, 20s, 30s backoff
        logger.warning("Rate limited, retrying in %ds", wait)
        await asyncio.sleep(wait)
        continue
    resp.raise_for_status()
    break
```

- **429 (Rate Limit):** Auto-retry up to 3× with 10/20/30s backoff
- **503 (Overloaded):** Same retry logic — Google Gemini overload spikes are temporary
- **After 3 retries:** Exception raised ? orchestrator catches it ? 502 returned to frontend

---

## Common Patterns Across All Agents

| Pattern | How It's Applied |
|---------|-----------------|
| `client_id` forced after parse | All 3 agents do `raw["client_id"] = client_id` after LLM parse — LLM cannot accidentally output wrong client |
| Position forced after parse | Debate agents set `raw["position"] = "risk_confirmed"/"false_positive"` — prevents role-swap bugs |
| `responseMimeType: application/json` | All agents request JSON output from Gemini REST API |
| Schema hint in prompt | `## Required Output Schema` section in every prompt — belt-and-suspenders alongside API-level format enforcement |
| Timeout 120s | All agents use `httpx.AsyncClient(timeout=120.0)` — LLM calls for long prompts can take 30-60s |
