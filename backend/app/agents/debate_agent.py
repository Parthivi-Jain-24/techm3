"""Stage 3 — Adversarial cross-check: prosecutor, defender, and judge.

Takes an ``InvestigationFinding`` from Stage 2, runs three sequential
LLM calls (prosecutor → defender → judge), and returns a ``DebateResult``
containing all three outputs plus the final verdict.

The prosecutor and defender run in parallel (they only need the finding);
the judge runs after both, receiving the finding plus both arguments.

Uses Google Gemini 2.5 Flash free tier via Google AI Studio API.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import httpx
from pydantic import BaseModel

from app.config import settings
from app.schemas.debate import DebateArgument, DebateVerdict
from app.schemas.findings import InvestigationFinding

logger = logging.getLogger(__name__)

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

# ── System prompts (verbatim from spec) ─────────────────────────────

PROSECUTOR_PROMPT = """\
You are the Prosecutor in an adversarial compliance review. Your role is to argue that a client represents a GENUINE compliance risk requiring escalation.

RULES:
1. Build the strongest evidence-based case FOR risk, using only the investigation findings provided.
2. Every point must cite a specific piece of evidence (source_id) from the findings — no speculation.
3. Do not soften or hedge your argument, but do not fabricate evidence either.
4. Address the strength of sanctions matches, transaction patterns, and any adverse indicators directly.
5. Keep the argument focused and evidence-dense, not repetitive.
Output ONLY valid JSON matching the DebateArgument schema with position="risk_confirmed"."""

DEFENDER_PROMPT = """\
You are the Defender in an adversarial compliance review. Your role is to argue that this client is likely a FALSE POSITIVE and does not require escalation.

RULES:
1. Build the strongest case that flagged evidence is weak, coincidental, or explainable — e.g. name collisions without matching DOB/nationality, resolved historical issues, transactions consistent with normal business activity for this sector.
2. Every point must cite specific evidence (source_id) or explicitly note the ABSENCE of corroborating evidence (e.g. "no DOB match found despite name similarity").
3. Do not dismiss real red flags dishonestly — if evidence is genuinely strong, acknowledge it but argue for the weakest reasonable interpretation.
4. Keep the argument focused and evidence-based, not reflexively skeptical.
Output ONLY valid JSON matching the DebateArgument schema with position="false_positive"."""

JUDGE_PROMPT = """\
You are the Judge in an adversarial compliance review. You have been given an investigation finding, a Prosecutor argument, and a Defender argument.

RULES:
1. Evaluate both arguments strictly on the evidence cited, not on rhetorical strength.
2. Decide: does this client require a SAR (Suspicious Activity Report), further investigation, or should it be cleared as a false positive?
3. Explain your reasoning in plain language a compliance officer could read and understand in under 30 seconds.
4. Assign a confidence score reflecting how clear-cut the evidence is (low confidence = genuinely ambiguous case, human review strongly advised).
5. Never invent evidence not present in either argument or the original findings.
Output ONLY valid JSON matching the DebateVerdict schema, with verdict one of: "escalate_to_sar", "further_investigation", "false_positive_clear"."""


# ── Return type ─────────────────────────────────────────────────────

class DebateResult(BaseModel):
    """Combined output of the full adversarial cross-check."""

    finding: InvestigationFinding
    prosecution: DebateArgument
    defense: DebateArgument
    verdict: DebateVerdict


# ── LLM helpers ─────────────────────────────────────────────────────

_ARGUMENT_SCHEMA = DebateArgument.model_json_schema()
_VERDICT_SCHEMA = DebateVerdict.model_json_schema()


async def _llm_call(
    system_prompt: str,
    user_prompt: str,
    schema: dict[str, Any],
    schema_name: str,
) -> dict:
    url = GEMINI_API_URL.format(model=settings.model_name)

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": system_prompt + "\n\n" + user_prompt}],
            }
        ],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0.3,
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
    return json.loads(content)


# ── Prompt builders ─────────────────────────────────────────────────

def _finding_block(finding: InvestigationFinding) -> str:
    return (
        "## Investigation Finding\n"
        + finding.model_dump_json(indent=2)
        + "\n\n## Required Output Schema\n"
    )


def _advocate_prompt(finding: InvestigationFinding, schema: dict) -> str:
    return (
        _finding_block(finding)
        + json.dumps(schema, indent=2)
        + "\n\nProduce your argument now. Cite source_ids from the evidence above."
    )


def _judge_prompt(
    finding: InvestigationFinding,
    prosecution: DebateArgument,
    defense: DebateArgument,
) -> str:
    return (
        _finding_block(finding)
        + "## Prosecutor Argument\n"
        + prosecution.model_dump_json(indent=2)
        + "\n\n## Defender Argument\n"
        + defense.model_dump_json(indent=2)
        + "\n\n## Required Output Schema\n"
        + json.dumps(_VERDICT_SCHEMA, indent=2)
        + "\n\nIssue your verdict now."
    )


# ── Public API ──────────────────────────────────────────────────────

async def run_debate(finding: InvestigationFinding) -> DebateResult:
    """Run the full prosecutor → defender → judge pipeline.

    Prosecutor and defender run concurrently (both only need the finding).
    The judge runs after both complete, receiving all three inputs.
    """

    prosecution_coro = _llm_call(
        PROSECUTOR_PROMPT,
        _advocate_prompt(finding, _ARGUMENT_SCHEMA),
        _ARGUMENT_SCHEMA,
        "DebateArgument",
    )
    defense_coro = _llm_call(
        DEFENDER_PROMPT,
        _advocate_prompt(finding, _ARGUMENT_SCHEMA),
        _ARGUMENT_SCHEMA,
        "DebateArgument",
    )

    raw_prosecution, raw_defense = await asyncio.gather(
        prosecution_coro, defense_coro
    )

    raw_prosecution["position"] = "risk_confirmed"
    raw_defense["position"] = "false_positive"

    prosecution = DebateArgument.model_validate(raw_prosecution)
    defense = DebateArgument.model_validate(raw_defense)

    raw_verdict = await _llm_call(
        JUDGE_PROMPT,
        _judge_prompt(finding, prosecution, defense),
        _VERDICT_SCHEMA,
        "DebateVerdict",
    )
    verdict = DebateVerdict.model_validate(raw_verdict)

    return DebateResult(
        finding=finding,
        prosecution=prosecution,
        defense=defense,
        verdict=verdict,
    )
