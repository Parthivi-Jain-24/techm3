"""Stage 2 — LLM-powered investigation agent.

Pulls client profile, transactions, and sanctions matches via data loaders,
builds a prompt with that context, calls Google Gemini 2.5 Flash (free tier
via Google AI Studio), and returns a validated ``InvestigationFinding``.
"""

from __future__ import annotations

import json
import logging

import httpx

from app.config import settings
from app.data_loaders import (
    get_client_profile,
    get_client_transactions,
    get_sanctions_matches,
)
from app.schemas.findings import InvestigationFinding

logger = logging.getLogger(__name__)

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

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


def _build_user_prompt(
    client_id: int,
    profile: dict,
    transactions: list[dict],
    sanctions: list[dict],
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

    parts.append(f"\n## Required Output Schema")
    parts.append(_SCHEMA_HINT)

    parts.append(
        "\nProduce the InvestigationFinding JSON for this client. "
        "Remember: every claim must cite a source_id."
    )
    return "\n".join(parts)


def _gather_context(client_id: int) -> tuple[dict | None, list[dict], list[dict]]:
    profile = get_client_profile(client_id)
    transactions = get_client_transactions(client_id)
    sanctions: list[dict] = []
    if profile:
        name = profile.get("client_name", "")
        if name:
            sanctions = get_sanctions_matches(name)
    return profile, transactions, sanctions


async def investigate(client_id: int) -> InvestigationFinding:
    """Run a full investigation for *client_id* and return a validated finding."""

    profile, transactions, sanctions = _gather_context(client_id)

    if profile is None:
        return InvestigationFinding(
            client_id=client_id,
            summary=f"No KYC profile found for client_id={client_id}. Cannot investigate.",
            confidence="low",
        )

    user_prompt = _build_user_prompt(client_id, profile, transactions, sanctions)

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
    raw["client_id"] = client_id

    return InvestigationFinding.model_validate(raw)
