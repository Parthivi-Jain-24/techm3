# Contributing

Five developers work independently on separate branches within this modular monorepo. Follow this workflow closely to minimize merge conflicts and keep `main` stable.

## Branch Naming Convention

```
main
develop

feature/secure-data-identity
feature/entity-intelligence
feature/risk-intelligence
feature/autonomous-investigation
feature/human-review-dashboard
```

Optional sub-feature branches:

```
feature/ingestion-pipeline
feature/ofac-screening
feature/entity-resolution
feature/aml-classifier
feature/risk-timeline
feature/investigation-agent
feature/sar-generator
feature/case-dashboard
```

## Git Workflow

1. Initial repository structure is created and committed to `main`.
2. `develop` is created from `main`.
3. Each developer creates their feature branch from the latest `develop`.
4. Developers work only within their owned modules where possible (see [CODEOWNERS](.github/CODEOWNERS)).
5. Shared contracts (see [docs/architecture/integration-contracts.md](docs/architecture/integration-contracts.md)) are agreed before implementation.
6. Each feature branch opens a pull request into `develop`.
7. CI runs tests and checks.
8. Integration testing happens on `develop`.
9. Stable `develop` is merged into `main`.

### Initial setup

```bash
git checkout main
git pull origin main

git checkout -b develop
git push -u origin develop
```

### Per-developer workflow

```bash
git checkout develop
git pull origin develop
git checkout -b feature/<workstream-name>
git push -u origin feature/<workstream-name>
```

### Before opening a PR

```bash
git checkout develop
git pull origin develop

git checkout feature/<workstream-name>
git merge develop

# Resolve conflicts locally.
# Run tests.
# Push changes.
# Open PR into develop.
```

## Pull Request Rules

- No direct pushes to `main`. `main` only receives merges from stable `develop`.
- No direct pushes to `develop` outside of approved PRs.
- Always pull the latest `develop` before starting new work.
- Rebase or merge `develop` into your feature branch before opening a PR — resolve conflicts locally, never in the PR UI for anything non-trivial.
- Keep PRs scoped to a single workstream/module where possible.
- Cross-module changes (touching files under [Shared File Rule](README.md) or another workstream's directory) require review from the owning workstream.

## Testing Requirements

- New backend modules require unit tests under `backend/tests/unit/`.
- Cross-module flows require integration tests under `backend/tests/integration/`.
- Auth, RBAC, PII masking, and audit logic require security tests under `backend/tests/security/`.
- Frontend features require component-level tests colocated with the feature.
- CI (`.github/workflows/ci.yml`) must pass before merge.

## Secret Scanning Reminder

- Never commit `.env` files, API keys, database passwords, JWT secrets, or cloud credentials.
- Run a secret scan locally before pushing if your tooling supports it.
- If a secret is accidentally committed, rotate it immediately and notify the team — do not just delete the commit.
