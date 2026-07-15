# Agents

**Owner:** Workstream 4 (Agent Orchestration, Autonomous Investigation, Evidence Grounding, Privacy Guardrails, SAR Drafting)

## Purpose

Orchestrate autonomous agent workflows that trigger investigations on high-risk events, ground findings in evidence, draft SARs, and enforce privacy guardrails on agent behavior.

## Structure

- `orchestrator/` — top-level workflow orchestration between agents.
- `monitoring_agent/` — watches risk/entity signals for trigger conditions.
- `investigation_agent/` — conducts autonomous investigation steps.
- `risk_agent/` — interprets risk assessments for agent decision-making.
- `sar_agent/` — drafts evidence-grounded SARs.
- `privacy_guardrail/` — enforces data minimization/masking constraints on agent tool calls.
- `tool_registry/` — scoped, least-privilege tool definitions agents may call (never raw DB access).

## Inputs

`Risk Assessment` records from `risk_intelligence/` (Workstream 3), `Entity Intelligence Result` records from `entity_intelligence/` (Workstream 2).

## Outputs

`Investigation Case` records (status, summary, evidence, SAR draft reference) consumed by `cases/` (Workstream 5) for human review.

## Public Interface Expectations

All agent actions must go through `tool_registry/` — no direct database sessions inside agent logic. All SAR drafts must cite `evidence_ids` from `backend/app/evidence/`.

## Security Considerations

- Agents must not receive unrestricted database access (see `SECURITY.md`).
- High-impact actions (SAR submission, case closure) are drafted here but require human approval in `backend/app/cases/review/`.
- LLM calls go through `backend/app/integrations/llm/` abstraction — never call a provider SDK directly from agent code.

## Integration Dependencies

- `backend/app/evidence/` for grounding.
- `backend/app/integrations/llm/` for model access.
- `backend/app/cases/` for handoff to human review.
