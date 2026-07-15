# Security Policy

This project handles concepts and workflows relevant to real banking compliance (KYC/AML). This repository, however, is a hackathon scaffold and must never contain real customer data or production secrets.

## Core Rules

1. **No real customer PII.** Only synthetic, clearly-fake sample data may be used, and only in small quantities for local development/testing.
2. **No secrets in Git.** API keys, database credentials, JWT signing keys, cloud credentials, and third-party tokens are provided via environment variables only (see `.env.example`). Never hardcode or commit them.
3. **Data minimization.** Every module and API contract should expose only the fields required for its consumers to do their job — no raw sensitive identifiers passed further than necessary.
4. **Least privilege.** Service accounts, API routes, database roles, and AI agents are granted the minimum access required for their function. No component should have blanket database access.
5. **AI agents must not receive unrestricted database access.** Agents interact with data through scoped services/tools defined in `backend/app/agents/tool_registry/`, never through direct, unrestricted database sessions.
6. **High-impact decisions require human review.** Autonomous agents may draft investigations, risk assessments, and SARs, but final submission, case closure, and any customer-impacting action require explicit human approval via the review workflow (`backend/app/cases/review/`).
7. **Audit everything.** User, agent, model, and system actions relevant to a case must be recorded through `backend/app/audit/`. Logs must never contain raw PII or secrets — use the masking utilities in `backend/app/privacy/masking/`.

## Reporting a Vulnerability

This is a hackathon project without a production deployment. If you discover a security issue in this repository (e.g., an accidentally committed secret, a sample dataset containing real-looking PII, or a design flaw):

1. Do not open a public issue describing exploit details.
2. Notify the team directly (project lead / repository admin) with a description of the issue and steps to reproduce.
3. If a secret was committed, rotate/revoke it immediately, independent of the disclosure process.
4. Allow the team to remediate before any public discussion of the issue.

## Out of Scope for This Stage

The following are intentionally not present in this scaffold and should not be added without explicit team discussion:

- Real KYC, AML, sanctions, or adverse media datasets.
- Trained ML models or model weights.
- Real API keys or credentials of any kind.
- Claims of production-grade security certification (e.g., SOC 2, PCI-DSS compliance) — this is a hackathon prototype, not an audited system.
