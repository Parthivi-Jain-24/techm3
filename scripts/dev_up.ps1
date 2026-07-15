# Boot every backend service on its own port, each from the working directory
# it requires. Usage:  powershell -File scripts\dev_up.ps1
#
# WHY THIS SCRIPT EXISTS — the two-`app`-packages problem:
# `app/` (Part 1, repo root) and `backend/app/` (Part 4) are both importable as
# `app`. Part 4's internal imports say `from app...` and only resolve correctly
# when uvicorn runs WITH backend/ as the working directory; from the repo root,
# Part 1's package shadows it and Part 4's agents break with ImportErrors.
# Until the team renames one package, this launcher encodes the rule so nobody
# has to remember it.
#
#   :8001  Part 1  Secure Data & Identity   (app.main, repo root)
#   :8002  Part 4  Investigation + SAR      (app.main, backend/ cwd)
#   :8003  Part 3+5 Risk + Governance       (risk_engine.api)
#   :8004  Part 2  Entity Intelligence      (projecttechm.api)

param(
    # Skip the React dev server (e.g. no Node installed, or API-only demo).
    [switch]$SkipFrontend
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$py = Join-Path $root ".venv\Scripts\python.exe"

if (-not (Test-Path $py)) { throw "Virtual environment not found. Create it first with: py -3 -m venv .venv" }
Write-Host "Checking Python dependencies..."
& $py -m pip install -q -r (Join-Path $root "requirements.txt") -r (Join-Path $root "backend\requirements.txt") -e $root
if ($LASTEXITCODE -ne 0) { throw "Python dependency installation failed." }

# --- Part 1 needs a JWT secret and at least one demo user (it is default-deny).
# DEV ONLY: these values are for local demos, never production.
if (-not $env:JWT_SECRET_KEY) {
    $env:JWT_SECRET_KEY = "dev-only-secret-" + [guid]::NewGuid().ToString("N")
    Write-Host "JWT_SECRET_KEY not set - generated a dev-only one for this session"
}
if (-not $env:DEV_AUTH_USERS) {
    $hash = & $py -c "from app.identity.authentication.password import hash_password; print(hash_password('CorrectHorse9!'))"
    $env:DEV_AUTH_USERS = '[{"username":"analyst","principal_id":"user-analyst-1","password_hash":"' + $hash + '","principal_type":"user","roles":["compliance_analyst"],"is_active":true}]'
    Write-Host "DEV_AUTH_USERS not set - seeded demo user analyst / CorrectHorse9!"
}

# --- Part 4's LLM: default to the local Ollama model (free, no key, no egress).
# Point LLM_BASE_URL / MODEL_NAME elsewhere for a hosted provider.
if (-not $env:LLM_MODE)     { $env:LLM_MODE = "demo" }
if (-not $env:LLM_BASE_URL) { $env:LLM_BASE_URL = "http://localhost:11434/v1" }
if (-not $env:MODEL_NAME)   { $env:MODEL_NAME = "qwen2.5:7b" }

# --- Audit log: ONE FILE PER PROCESS.
# The hash-chained sink keeps its previous_hash pointer in memory and documents
# that it does not coordinate across OS processes (app/audit/storage/jsonl.py).
# :8001 and :8002 both run Part 1's audit middleware, so pointing them at one
# file forks the chain (two lines sharing a previous_hash) and verification then
# fails on honest data. Give each service its own log. Both stay inside the
# approved runtime dir, so resolve_audit_log_path()'s containment check holds.
# Same reason: do NOT add `--workers N` here without making the sink
# multi-process safe first.
Write-Host ""
Write-Host "Starting services..."
$env:AUDIT_LOG_PATH = "backend/var/audit/audit.jsonl"
Start-Process -WorkingDirectory $root -FilePath $py -ArgumentList "-m","uvicorn","app.main:app","--port","8001"
$env:AUDIT_LOG_PATH = "backend/var/audit/investigation.jsonl"
Start-Process -WorkingDirectory (Join-Path $root "backend") -FilePath $py -ArgumentList "-m","uvicorn","app.main:app","--port","8002"
$env:AUDIT_LOG_PATH = "backend/var/audit/audit.jsonl"
Start-Process -WorkingDirectory $root -FilePath $py -ArgumentList "-m","uvicorn","risk_engine.api:app","--port","8003"
Start-Process -WorkingDirectory $root -FilePath $py -ArgumentList "-m","uvicorn","projecttechm.api:app","--port","8004"

# --- Frontend (React + Vite). Proxies /api -> :8002 (see frontend/vite.config.js).
# Covers the investigation dashboard only; Parts 1/2/3/5 are API-only (use /docs).
$frontend = Join-Path $root "frontend"
if (-not $SkipFrontend) {
    if (-not (Test-Path (Join-Path $frontend "node_modules"))) {
        Write-Host "Installing frontend dependencies (first run only)..."
        Start-Process -WorkingDirectory $frontend -FilePath "npm" -ArgumentList "install","--no-audit","--no-fund" -Wait -NoNewWindow
    }
    Start-Process -WorkingDirectory $frontend -FilePath "npm" -ArgumentList "run","dev"
}

Write-Host ""
Write-Host "  UI      Investigation Dashboard: http://localhost:5173        <-- start here"
Write-Host ""
Write-Host "  Part 1  Secure Data & Identity : http://127.0.0.1:8001/docs"
Write-Host "  Part 4  Investigation + SAR    : http://127.0.0.1:8002/docs"
Write-Host "  Part 3+5 Risk + Governance     : http://127.0.0.1:8003/docs"
Write-Host "  Part 2  Entity Intelligence    : http://127.0.0.1:8004/docs  (~40s startup: full sanctions coverage)"
Write-Host ""
Write-Host "  Part 1 login: analyst / CorrectHorse9!  (dev-only)"
Write-Host "  Note: the UI covers Part 4 only. Parts 1/2/3/5 are API-only -- use their /docs."
