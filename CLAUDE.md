# CLAUDE.md — Continuous KYC Autonomous Auditor

Project context for Claude Code, plus the skills reference for this machine.

---

## Running the project

```powershell
cd C:\Users\anike\Desktop\project\projecttechm
powershell -File scripts\dev_up.ps1        # starts all 5 services; -SkipFrontend for API-only
```

Execution policy here is `RemoteSigned`, so no `-ExecutionPolicy Bypass` is needed.

| Service | Port | Notes |
|---|---|---|
| UI (React + Vite) | http://localhost:5173 | Console for all five parts |
| Part 1 — Secure Data & Identity | 8001 | `/docs` |
| Part 4 — Investigation + SAR | 8002 | `/docs`; superset of Part 1's routes |
| Part 3+5 — Risk + Governance | 8003 | `/docs` |
| Part 2 — Entity Intelligence | 8004 | `/docs`; ~40s startup (1.29M entities) |

Dev login (Part 1): `analyst` / `CorrectHorse9!`. Tests: `.\.venv\Scripts\python -m pytest` (863 passing).

---

## Architecture

Part 1 (identity/ingestion) -> Part 2 (screening/UBO/adverse-media) -> Part 3 (risk)
-> Part 4 (investigation/debate/SAR) -> Part 5 (human review/governance), with a
hash-chained audit trail underneath.

Ownership: Part 2 is this workstream (`src/projecttechm/`). Parts 1/3/4/5 belong to
teammates — `app/`, `risk_engine/`, `backend/app/agents/`, `risk_engine/governance.py`.
Files headed `SHARED FILE — coordinate changes with all workstreams` need a heads-up
before editing.

---

## Traps (each one cost real debugging time)

- **Two `app` packages.** `app/` (Part 1, repo root) and `backend/app/` (Part 4 = Part 1's
  app + agents). Part 4 only runs with `backend/` as cwd, or Part 1's package shadows it.
  `dev_up.ps1` encodes this. A rename is the real fix — needs team agreement.
- **`PROJECT_ROOT` must stay marker-based.** It walks up to `.git`/`pyproject.toml`
  precisely because `app/core/config.py` exists at two depths; any hardcoded `parents[N]`
  is wrong in one of them. A previous `parents[3]` sent the audit log *outside* the repo.
- **Never point two services at one audit log.** The hash-chained sink is single-process
  by design (`app/audit/storage/jsonl.py`). Sharing a file forks the chain and verification
  fails on honest data. Same reason: **never add `--workers N`** without fixing the sink.
- **Never write to the runtime audit log from a test.** Use `git check-ignore` / `tmp_path`.
- **Empty scaffold dirs shadow real modules.** `agents/privacy_guardrail/` (0-byte
  `__init__.py`) silently beat `agents/privacy_guardrail.py`, and a try/except swallowed the
  ImportError — Part 4's routes vanished with no error.
- **Gitignored fixtures.** `data/kyc_profiles/client_account_mapping.csv` is `*.csv`-ignored
  and never committed; regenerate with `backend/scripts/generate_account_mapping.py` or the
  investigation pipeline dies on FileNotFoundError.
- **Vite proxies by path prefix** to four different backends — see `frontend/vite.config.js`.
- **Git Bash mangles paths.** Use `MSYS_NO_PATHCONV=1`; `scripts\x.ps1` becomes `scriptsx.ps1`.

## LLM policy

Part 4's agents are OpenAI-compatible and default to **local Ollama** (`qwen2.5:7b`) via
`LLM_BASE_URL` — free, no key, and **no customer data leaves the machine**. Point
`LLM_BASE_URL`/`MODEL_NAME` at a hosted provider only if that tradeoff is accepted.
Expect 2-4 min per investigation locally.

---

# Skills Reference

> Invoke a skill by typing `/<skill-name>` or by describing a task that matches its trigger.
>
> **Note:** This file only *documents* skills — it does not install them. The skills must exist
> in `~/.claude/skills/` or `.claude/skills/`. **As of this writing both directories are empty
> on this machine, so none of the non-built-in skills below are installed.** The built-in
> Claude Code skills at the bottom are always available.

## How to use skills

- **Explicit:** type `/skill-name` (e.g. `/python-pro`, `/code-review`).
- **Automatic:** describe the task — Claude matches it to a skill's trigger.
- **Prefer skills over ad-hoc work** when a task falls in a skill's domain.

## Languages & Frameworks

### Backend / Systems
- **python-pro** — Python 3.11+, type hints, async/await, pytest, mypy strict, ruff/black.
- **golang-pro** — Go concurrency (goroutines/channels), microservices, gRPC, pprof, generics.
- **rust-engineer** — idiomatic Rust, ownership/lifetimes, async tokio, traits, FFI.
- **cpp-pro** — modern C++20/23, templates, SIMD, memory management, CMake.
- **java-architect** — enterprise Java, Spring Boot 3.x, WebFlux, JPA, OAuth2/JWT.
- **csharp-developer** — C#/.NET 8+, ASP.NET Core, Blazor, EF Core, CQRS/MediatR.
- **dotnet-core-expert** — .NET 8 minimal APIs, clean architecture, AOT, microservices.
- **php-pro** — PHP 8.3+, strict typing, PHPStan L9, Swoole, PSR, Laravel/Symfony.
- **kotlin-specialist** — Kotlin coroutines, Flow, multiplatform (KMP), Compose, Ktor, DSLs.
- **swift-expert** — Swift language and Apple platform development.

### Web frameworks
- **fastapi-expert** — FastAPI, Pydantic V2, async SQLAlchemy, JWT, WebSockets, OpenAPI.
- **django-expert** — Django + DRF, ORM optimization, serializers/viewsets, JWT.
- **nestjs-expert** — NestJS modules/controllers/services, DI, guards, TypeORM/Prisma.
- **rails-expert** — Rails 7+, Active Record, Hotwire/Turbo, Action Cable, Sidekiq, RSpec.
- **laravel-specialist** — Laravel 10+, Eloquent, Sanctum, Horizon, Livewire.
- **spring-boot-engineer** — Spring Boot services and patterns.
- **nextjs-developer** — Next.js 14+ App Router, RSC, server actions, streaming SSR, Vercel.
- **wordpress-pro** — WordPress development.
- **shopify-expert** — Shopify apps and themes.
- **salesforce-developer** — Apex, Lightning Web Components, SOQL, triggers, Salesforce DX.

### Frontend / Mobile
- **react-expert** — React 18/19, hooks, Server Components, Suspense, performance.
- **vue-expert** — Vue (TypeScript).
- **vue-expert-js** — Vue (JavaScript).
- **angular-architect** — Angular 17+ standalone components, signals, NgRx, RxJS.
- **typescript-pro** — advanced TypeScript across the stack.
- **javascript-pro** — modern ES2023+, async patterns, ESM, Node.js APIs.
- **flutter-expert** — Flutter 3+/Dart, Riverpod/Bloc, GoRouter, cross-platform.
- **react-native-expert** — React Native/Expo, navigation, native modules, FlatList perf.
- **lovable** — polished React + Vite + Tailwind + TS apps, design-system-first.

## Architecture & Design
- **architecture-designer** — system architecture, ADRs, tech trade-offs, scalability.
- **api-designer** — REST/GraphQL design, OpenAPI specs, versioning, pagination.
- **graphql-architect** — GraphQL schemas, Apollo Federation, DataLoader, subscriptions.
- **microservices-architect** — decompose monoliths, DDD, sagas, event sourcing, CQRS.
- **cloud-architect** — AWS/Azure/GCP architecture, migrations, cost, DR, Well-Architected.
- **legacy-modernizer** — incremental migration, strangler fig, framework upgrades.

## Data, ML & AI
- **pandas-pro** — pandas DataFrames: cleaning, joins, pivots, time series, groupby.
- **ml-pipeline** — MLOps: MLflow/W&B, Kubeflow/Airflow, feature stores, retraining.
- **rag-architect** — RAG systems: chunking, embeddings, vector stores, reranking, eval.
- **fine-tuning-expert** — LoRA/QLoRA, PEFT, dataset prep, RLHF/DPO, quantization.
- **prompt-engineer** — prompt design, structured output schemas, eval rubrics.
- **spark-engineer** — Apache Spark data engineering.

## Databases
- **sql-pro** — SQL query authoring and optimization.
- **postgres-pro** — PostgreSQL: EXPLAIN, JSONB, extensions, VACUUM, replication.
- **database-optimizer** — cross-DB query tuning, index design, partitioning, locks.

## DevOps, Infra & Reliability
- **devops-engineer** — Dockerfiles, CI/CD, Kubernetes manifests, Terraform, GitOps.
- **kubernetes-specialist** — K8s deployments, RBAC, NetworkPolicies, Helm, debugging.
- **terraform-engineer** — Terraform infrastructure as code.
- **sre-engineer** — SLIs/SLOs, error budgets, incident response, capacity planning.
- **chaos-engineer** — chaos experiments, fault injection, game days, resilience testing.
- **monitoring-expert** — Prometheus/Grafana, structured logging, tracing, load testing.

## Testing & QA
- **test-master** — comprehensive test strategy and authoring.
- **playwright-expert** — E2E browser tests, Page Object Model, visual regression, CI.

## Security
- **security-reviewer** — security-focused review.
- **secure-code-guardian** — authn/authz, input validation, OWASP Top 10 prevention.
- **fullstack-guardian** — security-focused full-stack features, DB->UI, layered defense.

## Code Quality & Debugging
- **code-reviewer** — broad PR review: bugs, security, smells, N+1, architecture.
- **code-documenter** — docstrings, OpenAPI/Swagger, JSDoc, doc portals, guides.
- **debugging-wizard** — stack traces, log correlation, hypothesis-driven root cause.

## Tooling & Integrations
- **cli-developer** — CLI tools, arg parsing, prompts, progress bars, shell completions.
- **mcp-developer** — build/debug MCP servers & clients (TypeScript/Python SDKs).
- **websocket-engineer** — WebSocket/real-time systems.
- **atlassian-mcp** — Jira (JQL), Confluence (CQL), sprints via MCP.

## Requirements & Product
- **feature-forge** — requirements workshops, user stories, EARS specs, acceptance criteria.
- **spec-miner** — extract specifications.

## Specialized Domains
- **game-developer** — Unity/Unreal, ECS, physics, multiplayer netcode, shaders, 60+ FPS.
- **embedded-systems** — firmware, STM32/ESP32, FreeRTOS, interrupts, DMA, power tuning.
- **the-fool** — contrarian / lateral-thinking perspective.

---

## Built-in Claude Code skills (always available — no install needed)

- **/init** — bootstrap/refresh this project's CLAUDE.md.
- **/code-review** — review the current diff (low->max effort; `ultra` for cloud multi-agent).
- **/simplify** — apply reuse/simplification/efficiency cleanups to changed code.
- **/security-review** — security review of pending branch changes.
- **/review** — general review.
- **/verify** — exercise a change end-to-end to confirm it works.
- **/run** — launch and drive this project's app.
- **/deep-research** — multi-source, fact-checked research report.
- **/dataviz** — read before building any chart/graph/dashboard.
- **/artifact-design** — design guidance for Artifacts.
- **/claude-api** — reference for Claude API / Anthropic SDK (models, pricing, tools).
- **/prompt-engineer** — prompt authoring & eval.
- **/update-config** — configure the harness via settings.json (hooks, permissions, env).
- **/keybindings-help** — customize keyboard shortcuts.
- **/fewer-permission-prompts** — build a Bash/MCP allowlist to reduce prompts.
- **/loop** — run a prompt/command on a recurring interval.
- **/schedule** — create/manage scheduled cloud agents (cron routines).
