"""Stage 4 -- SAR (Suspicious Activity Report) drafting agent.

Takes a grounding-guardrail-verified ``InvestigationFinding`` and a
``DebateVerdict`` whose outcome is ``escalate_to_sar``, calls Google
Gemini 2.5 Flash (free tier via Google AI Studio) to produce a structured
``SARDraft``, then runs the grounding guardrail and privacy guardrail
before returning.

Pipeline position::

    InvestigationFinding + DebateVerdict
        -> LLM drafting call
        -> verify_sar()         (grounding guardrail)
        -> redact_sar()         (privacy guardrail)
        -> SARResult
"""

from __future__ import annotations

import json
import logging

import httpx
from pydantic import BaseModel

from app.config import settings
from app.schemas.sar import SARDraft
from app.schemas.findings import InvestigationFinding
from app.schemas.debate import DebateVerdict
from app.agents.grounding_guardrail import verify_sar, GuardrailResult
from app.agents.privacy_guardrail import redact_sar, PrivacyGuardrailResult

logger = logging.getLogger(__name__)

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

# ── System prompt (verbatim from spec) ─────────────────────────────

SYSTEM_PROMPT = """\
You are a Suspicious Activity Report (SAR) drafting assistant for a financial compliance team. You draft REPORTS FOR HUMAN REVIEW — you do not file anything yourself, and every draft must be clearly marked as requiring compliance officer sign-off.

RULES:
1. Follow standard SAR structure: Subject Information, Suspicious Activity Narrative, Red Flags Identified, Regulatory Basis, Recommended Action.
2. Every factual claim in the narrative MUST cite a source_id from the evidence provided (transaction_id, sanctions record, profile field).
3. Do not include unnecessary PII (full DOB, full account numbers) — reference the privacy-guardrail-redacted fields provided to you; never re-introduce raw PII yourself.
4. For "Regulatory Basis," cite the specific GDPR article number(s) provided to you if data-handling justification is relevant; otherwise note the AML reporting obligation generically (do not invent a specific non-GDPR statute/citation).
5. Write the narrative in clear, formal, factual compliance language — no dramatization, no hedging beyond what the confidence scores support.
6. Include a disclaimer field noting this is an AI-generated draft requiring human compliance officer review before filing.
Output ONLY valid JSON matching the SARDraft schema."""


# ── Return type ────────────────────────────────────────────────────

class SARResult(BaseModel):
    """Combined output of Stage 4: draft + guardrail reports."""

    sar: SARDraft
    grounding: GuardrailResult
    privacy: PrivacyGuardrailResult


# ── Prompt builder ─────────────────────────────────────────────────

_SAR_SCHEMA = SARDraft.model_json_schema()
_SCHEMA_HINT = json.dumps(_SAR_SCHEMA, indent=2)


def _build_user_prompt(
    finding: InvestigationFinding,
    verdict: DebateVerdict,
) -> str:
    parts: list[str] = []

    parts.append("## Investigation Finding")
    parts.append(finding.model_dump_json(indent=2))

    parts.append("\n## Debate Verdict")
    parts.append(verdict.model_dump_json(indent=2))

    parts.append("\n## Required Output Schema")
    parts.append(_SCHEMA_HINT)

    parts.append(
        "\nDraft the SARDraft JSON now. "
        "Every narrative claim must cite a source_id from the evidence above. "
        "Do not re-introduce raw PII — use redacted placeholders where appropriate."
    )
    return "\n".join(parts)


# ── Public API ─────────────────────────────────────────────────────

async def draft_sar(
    finding: InvestigationFinding,
    verdict: DebateVerdict,
) -> SARResult:
    """Draft a SAR from a verified finding and an escalation verdict.

    The LLM produces a raw ``SARDraft``, which is then run through:

    1. ``verify_sar()`` — grounding guardrail strips unverifiable
       evidence citations.
    2. ``redact_sar()`` — privacy guardrail redacts PII and appends
       GDPR article references.
    """

    user_prompt = _build_user_prompt(finding, verdict)

    url = GEMINI_API_URL.format(model=settings.model_name)

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": SYSTEM_PROMPT + "\n\n" + user_prompt}],
            }
        ],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0.2,
        },
    }

    params = {"key": settings.gemini_api_key}

    import asyncio as _asyncio

    async with httpx.AsyncClient(timeout=120.0) as client:
        for attempt in range(4):
            resp = await client.post(url, json=payload, params=params)
            if resp.status_code in (429, 503) and attempt < 3:
                wait = (attempt + 1) * 10
                logger.warning("Rate limited (429), retrying in %ds (attempt %d/3)", wait, attempt + 1)
                await _asyncio.sleep(wait)
                continue
            if resp.status_code != 200:
                logger.error("Gemini API error %s: %s", resp.status_code, resp.text)
            resp.raise_for_status()
            break

    body = resp.json()
    content = body["candidates"][0]["content"]["parts"][0]["text"]

    raw = json.loads(content)
    raw["client_id"] = finding.client_id

    draft = SARDraft.model_validate(raw)

    grounded, grounding_result = verify_sar(draft)
    logger.info(
        "SAR grounding: %d verified, %d stripped, %d skipped",
        grounding_result.verified_count,
        grounding_result.stripped_count,
        grounding_result.skipped_count,
    )

    redacted, privacy_result = redact_sar(grounded)
    logger.info(
        "SAR privacy: %d redactions applied",
        privacy_result.redaction_count,
    )

    return SARResult(
        sar=redacted,
        grounding=grounding_result,
        privacy=privacy_result,
    )
