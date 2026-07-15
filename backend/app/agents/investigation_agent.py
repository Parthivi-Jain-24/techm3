"""Stage 2 — LLM-powered investigation agent.

Pulls client profile, transactions, and sanctions matches via data loaders,
builds a prompt with that context, calls NVIDIA GLM-5.2 via OpenAI-compatible
API, and returns a validated ``InvestigationFinding``.
"""

from __future__ import annotations

import json
import logging
import re


from app.config import settings
from app.data_loaders import (
    get_client_profile,
    get_client_transactions,
    get_sanctions_matches,
    get_adverse_media,
)
from app.schemas.findings import InvestigationFinding
from app.agents.demo_pipeline import demo_finding

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a Continuous KYC Investigation Agent for a financial compliance system.

Your job: given a corporate client's profile, transaction history, and sanctions match data, produce a structured investigation finding.

RULES:
1. Every factual claim you make MUST cite a specific evidence source: a transaction_id, a sanctions record_id, or a specific field from the client profile (e.g. "sector_risk=High").
2. Never state a claim you cannot trace to the provided data. If evidence is insufficient to support a conclusion, say so explicitly rather than guessing.
3. Distinguish between confirmed facts (directly from data) and inferences (your reasoning connecting facts). Label inferences clearly.
4. If sanctions name matches exist, evaluate whether the match is likely a true match or a coincidental name collision, using available disambiguating fields (DOB, nationality, aliases, sector).
5. Look for patterns across transactions (repeated structuring, unusual cross-border activity, timing clusters) rather than treating transactions independently.
6. Output ONLY valid JSON matching the InvestigationFinding schema. No preamble, no explanation outside the JSON."""

_SCHEMA_HINT = json.dumps(InvestigationFinding.model_json_schema(), indent=2)

_MAX_TRANSACTIONS_IN_PROMPT = 50


def _extract_json(text: str) -> str:
    """Strip markdown code fences if the model wraps output in ```json ... ```."""
    text = text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    if match:
        return match.group(1).strip()
    return text


def _build_user_prompt(
    client_id: int,
    profile: dict,
    transactions: list[dict],
    sanctions: list[dict],
    news: list[dict],
) -> str:
    parts: list[str] = []

    parts.append(f"## Client Profile (client_id={client_id})")
    parts.append(json.dumps(profile, indent=2, default=str))

    parts.append(f"\n## Transactions ({len(transactions)} total)")
    if len(transactions) > _MAX_TRANSACTIONS_IN_PROMPT:
        parts.append(
            f"(Showing first {_MAX_TRANSACTIONS_IN_PROMPT} of {len(transactions)}; "
            "analyse the full pattern from these.)"
        )
    for txn in transactions[:_MAX_TRANSACTIONS_IN_PROMPT]:
        parts.append(json.dumps(txn, default=str))

    parts.append(f"\n## Sanctions Screening Matches ({len(sanctions)} hits)")
    if sanctions:
        for hit in sanctions:
            parts.append(json.dumps(hit, default=str))
    else:
        parts.append("No matches found.")

    parts.append(f"\n## Live Adverse Media News ({len(news)} articles found)")
    if news:
        for art in news:
            parts.append(json.dumps(art, default=str))
    else:
        parts.append("No adverse news found.")

    parts.append(f"\n## Required Output Schema")
    parts.append(_SCHEMA_HINT)

    parts.append(
        "\nProduce the InvestigationFinding JSON for this client. "
        "Remember: every claim must cite a source_id."
    )
    return "\n".join(parts)


def _gather_context(client_id: int) -> tuple[dict | None, list[dict], list[dict], list[dict]]:
    profile = get_client_profile(client_id)
    transactions = get_client_transactions(client_id)
    sanctions: list[dict] = []
    news: list[dict] = []
    if profile:
        name = profile.get("client_name", "")
        if name:
            sanctions = get_sanctions_matches(name)
            news = get_adverse_media(name)
    return profile, transactions, sanctions, news


async def investigate(client_id: int) -> InvestigationFinding:
    """Run a full investigation for *client_id* and return a validated finding."""

    if settings.llm_mode.lower() == "demo":
        return demo_finding(client_id)


    from openai import AsyncOpenAI

    profile, transactions, sanctions, news = _gather_context(client_id)

    if profile is None:
        return InvestigationFinding(
            client_id=client_id,
            summary=f"No KYC profile found for client_id={client_id}. Cannot investigate.",
            confidence="low",
        )

    user_prompt = _build_user_prompt(client_id, profile, transactions, sanctions, news)

    nvidia_client = AsyncOpenAI(
        base_url=settings.llm_base_url,
        # Local OpenAI-compatible servers (Ollama) ignore auth, but the client
        # requires a non-empty value.
        api_key=settings.nvidia_api_key or "not-needed",
    )

    logger.info("Calling NVIDIA GLM-5.2 for investigation (client_id=%d)", client_id)

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
    logger.debug("Raw LLM response: %s", content[:500])

    raw = json.loads(_extract_json(content))
    raw["client_id"] = client_id

    return InvestigationFinding.model_validate(raw)

