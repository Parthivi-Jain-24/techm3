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

(keep your existing repository tree here)

---

# Engineering Workstreams

(keep your existing workstream table here)

---

# Backend Setup

(keep your existing setup instructions here)

---

# Entity Intelligence Module

The Entity Intelligence module implements the core capabilities required for:

- Sanctions and watchlist screening
- Entity normalization
- Hybrid entity resolution
- Evidence-first compliance outputs
- Adverse media intelligence
- Ownership graph traversal for hidden beneficial ownership detection

---

# ProjectTechM Entity Intelligence Implementation

## What this project covers

- Sanctions and watchlist entity normalization
- Hybrid entity resolution with fuzzy + contextual scoring hooks
- Evidence-first output contracts for downstream risk and SAR workflows
- Adverse-media extraction with prompt-injection defense hooks
- Ownership graph traversal for hidden-UBO detection

---

# Suggested Structure

src/projecttechm/

├── schemas.py
├── scoring.py
├── resolution.py
├── adverse_media.py
├── ubo_graph.py
├── cli.py
├── api.py
├── evidence.py
├── audit.py
├── services.py


---

# Running Entity Intelligence Module

```bash
python -m venv .venv

.\.venv\Scripts\activate

pip install -e .[dev]

