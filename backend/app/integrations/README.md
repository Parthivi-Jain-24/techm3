# Integrations

**Owner:** Shared — each subdirectory is owned by the workstream that depends on it most heavily, but the abstraction pattern is common to all.

## Purpose

Isolate all third-party/external service access behind stable internal interfaces, so provider-specific details (LLM vendor, news API, sanctions data source) never leak into business logic.

## Structure

- `llm/` — LLM provider abstraction layer (owned by Workstream 4). Business logic calls this interface, never a provider SDK directly.
- `news/` — adverse media / news API integration (owned by Workstream 2).
- `sanctions/` — sanctions list / OpenSanctions / OFAC data source integration (owned by Workstream 2).
- `regulatory/` — regulatory/privacy dataset integration (owned by Workstream 1).

## Inputs

Configuration from `backend/app/core/config.py` (API keys via environment variables only — never hardcoded).

## Outputs

Normalized responses consumed by the owning workstream's domain modules (e.g., `entity_intelligence/`, `agents/`).

## Public Interface Expectations

Each integration should expose a small, typed interface (e.g., `LLMClient.generate(...)`) so the underlying provider can be swapped without touching callers.

## Security Considerations

- All credentials come from environment variables (see `.env.example`).
- No provider SDK should be called outside this directory.

## Integration Dependencies

- `backend/app/core/config.py` for credential access.
