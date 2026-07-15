# Continuous KYC Autonomous Auditor

A secure, explainable, multi-agent Continuous KYC platform for high-risk corporate accounts.

> **Status:** Active development. The repository establishes the modular monorepo structure for multiple engineering workstreams including secure ingestion, identity, privacy, entity intelligence, risk intelligence, autonomous investigation agents, evidence grounding, SAR generation, audit logging, and frontend workflows.

---

# Project Purpose

The Continuous KYC Autonomous Auditor continuously monitors high-risk corporate accounts by:

1. Securely ingesting KYC profiles, AML transaction data, sanctions lists, OFAC data, adverse media, and regulatory/privacy datasets.
2. Screening corporate entities and related persons against sanctions and watchlists.
3. Performing entity resolution to reduce false positives.
4. Monitoring transaction risk and AML patterns.
5. Maintaining continuous and explainable customer risk scores with risk timelines.
6. Triggering autonomous investigation workflows when high-risk events occur.
7. Generating evidence-grounded draft Suspicious Activity Reports (SARs).
8. Requiring human review for high-impact compliance decisions.
9. Maintaining complete audit trails of user, agent, model, and system actions.
10. Protecting sensitive customer information using least privilege access, masking, encryption-ready abstractions, secure authentication, authorization, and data minimization.

---

# High-Level Architecture

                +----------------+
                |   Data Sources |
                +----------------+
                        |
                        v
             +---------------------+
             | Secure Data Ingestion|
             +---------------------+
                        |
                        v
          +-----------------------------+
          | Identity & Privacy Protection |
          +-----------------------------+
                        |
                        v
          +-----------------------------+
          | Entity Intelligence          |
          | Resolution / Sanctions / AML |
          +-----------------------------+
                        |
                        v
          +-----------------------------+
          | Risk Intelligence            |
          | Scoring / Monitoring / ML     |
          +-----------------------------+
                        |
                        v
          +-----------------------------+
          | Agent Orchestration          |
          | Investigation Workflow       |
          +-----------------------------+
                        |
                        v
          +-----------------------------+
          | Evidence Grounding & SAR     |
          | Human Review                 |
          +-----------------------------+
                        |
                        v
          +-----------------------------+
          | Audit Trail & Governance     |
          +-----------------------------+


---

# Technology Stack

## Backend

- Python
- FastAPI
- Pydantic
- SQLAlchemy
- Alembic
- PostgreSQL

## Frontend

- React
- TypeScript
- Tailwind CSS
- Vite

## AI / ML

- scikit-learn
- pandas
- numpy
- sentence-transformers
- LLM provider abstraction layer
- Agent orchestration framework

---

# Repository Structure

techm-kyc/

│
├── backend/
│ ├── app/
│ │ ├── agents/
│ │ ├── api/
│ │ ├── audit/
│ │ ├── cases/
│ │ ├── core/
│ │ ├── database/
│ │ ├── encryption/
│ │ ├── entity_intelligence/
│ │ ├── evidence/
│ │ ├── identity/
│ │ ├── ingestion/
│ │ ├── integrations/
│ │ ├── privacy/
│ │ ├── risk_intelligence/
│ │ └── schemas/
│ │
│ ├── tests/
│ ├── requirements.txt
│ └── alembic.ini
│
├── frontend/
│ ├── src/
│ ├── public/
│ ├── package.json
│ └── vite.config.js
│
├── data/
│ ├── raw/
│ ├── processed/
│ ├── encrypted/
│ └── samples/
│
├── docs/
│
├── ml/
│
├── scripts/
│
├── deployment/
│
├── docker-compose.yml
│
└── README.md


---

# Engineering Workstreams

| Workstream | Scope | Primary Directories |
|---|---|---|
| 1 | Secure Data Ingestion, Authentication, Authorization, PII Protection, Database | `backend/app/ingestion/`, `backend/app/identity/`, `backend/app/privacy/`, `backend/app/database/` |
| 2 | Entity Resolution, Sanctions Screening, OFAC, Adverse Media Monitoring | `backend/app/entity_intelligence/`, `backend/app/integrations/` |
| 3 | AML Transaction Monitoring, ML Models, Risk Scoring, Confidence Scoring | `backend/app/risk_intelligence/`, `ml/` |
| 4 | Agent Orchestration, Autonomous Investigation, Evidence Grounding, SAR Drafting | `backend/app/agents/`, `backend/app/evidence/` |
| 5 | Frontend Dashboard, Case Management, Human Review Workflow, Audit UI | `frontend/`, `backend/app/cases/`, `backend/app/audit/` |

---

# Backend Setup

## Create Virtual Environment

```bash
cd backend

python -m venv .venv