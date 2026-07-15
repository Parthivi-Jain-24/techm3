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
import re

from openai import AsyncOpenAI
from pydantic import BaseModel

from app.config import settings
from app.schemas.sar import SARDraft
from app.schemas.findings import InvestigationFinding
from app.schemas.debate import DebateVerdict
from app.agents.grounding_guardrail import verify_sar, GuardrailResult
from app.agents.privacy_guardrail import redact_sar, PrivacyGuardrailResult

logger = logging.getLogger(__name__)

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

    nvidia_client = AsyncOpenAI(
        base_url=settings.llm_base_url,
        # Local OpenAI-compatible servers (Ollama) ignore auth, but the client
        # requires a non-empty value.
        api_key=settings.nvidia_api_key or "not-needed",
    )

    logger.info("Calling NVIDIA GLM-5.2 for SAR draft (client_id=%d)", finding.client_id)

    response = await nvidia_client.chat.completions.create(
        model=settings.model_name,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user_prompt},
        ],
        temperature=0.2,
        top_p=1,
        max_tokens=4096,
        seed=42,
    )

    content = response.choices[0].message.content
    logger.debug("Raw SAR LLM response: %s", content[:300])

    # Strip markdown code fences if model wraps output in ```json ... ```
    content = content.strip()
    import re as _re
    _match = _re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", content)
    if _match:
        content = _match.group(1).strip()

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
