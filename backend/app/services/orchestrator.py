"""Full-pipeline orchestrator — runs every stage in sequence for a
given ``client_id`` and returns a single ``PipelineResult`` containing
all intermediate outputs.

Pipeline stages executed in order:

1. **Investigation Agent** — gathers data, calls LLM, produces
   ``InvestigationFinding``.
2. **Grounding Guardrail** (``verify_finding``) — strips unverifiable
   evidence citations from the finding.
3. **Debate Agent** — prosecutor + defender (parallel) then judge,
   produces ``DebateResult``.
4. **Grounding Guardrail** (``verify_debate_argument`` × 2) — strips
   unverifiable citations from both debate arguments.
5. **SAR Agent** (only if verdict is ``escalate_to_sar``) — drafts a
   ``SARDraft``, then internally runs ``verify_sar`` + ``redact_sar``.

The ``PipelineResult`` carries every intermediate model plus guardrail
reports so the frontend can display the full reasoning trail.
"""

from __future__ import annotations

import logging
import time
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.findings import InvestigationFinding
from app.schemas.debate import DebateArgument, DebateVerdict
from app.schemas.sar import SARDraft
from app.agents.grounding_guardrail import (
    GuardrailResult,
    verify_finding,
    verify_debate_argument,
)
from app.agents.privacy_guardrail import PrivacyGuardrailResult
from app.agents.investigation_agent import investigate
from app.agents.debate_agent import run_debate
from app.agents.sar_agent import draft_sar

logger = logging.getLogger(__name__)


# ── Pipeline outcome enum ──────────────────────────────────────────

class PipelineOutcome(str, Enum):
    """Final disposition after the full pipeline."""

    ESCALATE_TO_SAR = "escalate_to_sar"
    FURTHER_INVESTIGATION = "further_investigation"
    FALSE_POSITIVE_CLEAR = "false_positive_clear"
    ERROR = "error"


# ── Stage-level result wrappers ────────────────────────────────────
# Each wraps one pipeline stage's output together with its guardrail
# report and timing, giving the frontend everything it needs to
# render that stage's panel.

class InvestigationStage(BaseModel):
    """Stage 2 output: LLM finding + grounding-guardrail report."""

    finding: InvestigationFinding
    guardrail: GuardrailResult
    duration_ms: int = Field(
        ..., description="Wall-clock time for this stage (ms)"
    )


class DebateStage(BaseModel):
    """Stage 3 output: full debate transcript + guardrail reports."""

    prosecution: DebateArgument
    prosecution_guardrail: GuardrailResult
    defense: DebateArgument
    defense_guardrail: GuardrailResult
    verdict: DebateVerdict
    duration_ms: int = Field(
        ..., description="Wall-clock time for this stage (ms)"
    )


class SARStage(BaseModel):
    """Stage 4 output: SAR draft + both guardrail reports."""

    sar: SARDraft
    grounding_guardrail: GuardrailResult
    privacy_guardrail: PrivacyGuardrailResult
    duration_ms: int = Field(
        ..., description="Wall-clock time for this stage (ms)"
    )


# ── Combined pipeline result ──────────────────────────────────────

class PipelineResult(BaseModel):
    """Everything produced by a single pipeline run.

    The frontend can display each stage's panel (investigation,
    debate transcript, SAR draft) with its guardrail reports and
    timing alongside the final outcome.
    """

    client_id: int
    outcome: PipelineOutcome

    investigation: InvestigationStage
    debate: DebateStage
    sar: Optional[SARStage] = Field(
        None,
        description="Present only when verdict is escalate_to_sar",
    )

    total_duration_ms: int = Field(
        ..., description="Wall-clock time for the full pipeline (ms)"
    )
    error: Optional[str] = Field(
        None,
        description="Error message if the pipeline failed mid-run",
    )


# ── Orchestrator ───────────────────────────────────────────────────

async def run_pipeline(client_id: int) -> PipelineResult:
    """Execute the full investigation pipeline for *client_id*.

    Returns a ``PipelineResult`` with every intermediate output
    regardless of whether the verdict leads to a SAR or not.
    """

    pipeline_start = time.perf_counter()

    # ── Stage 2: Investigation ─────────────────────────────────
    logger.info("Pipeline [%d] Stage 2: investigation starting", client_id)
    t0 = time.perf_counter()

    finding_raw = await investigate(client_id)
    finding, finding_gr = verify_finding(finding_raw)

    investigation_ms = int((time.perf_counter() - t0) * 1000)
    logger.info(
        "Pipeline [%d] Stage 2 done in %d ms "
        "(evidence: %d verified, %d stripped, %d skipped)",
        client_id,
        investigation_ms,
        finding_gr.verified_count,
        finding_gr.stripped_count,
        finding_gr.skipped_count,
    )

    investigation_stage = InvestigationStage(
        finding=finding,
        guardrail=finding_gr,
        duration_ms=investigation_ms,
    )

    # ── Stage 3: Adversarial Debate ────────────────────────────
    logger.info("Pipeline [%d] Stage 3: debate starting", client_id)
    t0 = time.perf_counter()

    debate_result = await run_debate(finding)

    # Ground-check both debate arguments against the verified
    # finding's evidence (transitive trust chain).
    prosecution, pros_gr = verify_debate_argument(
        debate_result.prosecution, finding,
    )
    defense, def_gr = verify_debate_argument(
        debate_result.defense, finding,
    )

    debate_ms = int((time.perf_counter() - t0) * 1000)
    logger.info(
        "Pipeline [%d] Stage 3 done in %d ms — verdict: %s",
        client_id,
        debate_ms,
        debate_result.verdict.verdict.value,
    )

    debate_stage = DebateStage(
        prosecution=prosecution,
        prosecution_guardrail=pros_gr,
        defense=defense,
        defense_guardrail=def_gr,
        verdict=debate_result.verdict,
        duration_ms=debate_ms,
    )

    # ── Stage 4: SAR (conditional) ─────────────────────────────
    sar_stage: SARStage | None = None
    outcome = PipelineOutcome(debate_result.verdict.verdict.value)

    if outcome == PipelineOutcome.ESCALATE_TO_SAR:
        logger.info("Pipeline [%d] Stage 4: SAR drafting starting", client_id)
        t0 = time.perf_counter()

        sar_result = await draft_sar(finding, debate_result.verdict)

        sar_ms = int((time.perf_counter() - t0) * 1000)
        logger.info(
            "Pipeline [%d] Stage 4 done in %d ms "
            "(grounding: %d verified / %d stripped, "
            "privacy: %d redactions)",
            client_id,
            sar_ms,
            sar_result.grounding.verified_count,
            sar_result.grounding.stripped_count,
            sar_result.privacy.redaction_count,
        )

        sar_stage = SARStage(
            sar=sar_result.sar,
            grounding_guardrail=sar_result.grounding,
            privacy_guardrail=sar_result.privacy,
            duration_ms=sar_ms,
        )
    else:
        logger.info(
            "Pipeline [%d] Skipping SAR — verdict is %s",
            client_id,
            outcome.value,
        )

    total_ms = int((time.perf_counter() - pipeline_start) * 1000)
    logger.info(
        "Pipeline [%d] complete in %d ms — outcome: %s",
        client_id,
        total_ms,
        outcome.value,
    )

    return PipelineResult(
        client_id=client_id,
        outcome=outcome,
        investigation=investigation_stage,
        debate=debate_stage,
        sar=sar_stage,
        total_duration_ms=total_ms,
    )
