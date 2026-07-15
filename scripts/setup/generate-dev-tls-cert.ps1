<#
.SYNOPSIS
    Generate a LOCAL, self-signed TLS development certificate for the Phase 7
    TLS 1.3 secure-demonstration listener. NOT for production use.

.DESCRIPTION
    Creates certs/local/dev-cert.pem and certs/local/dev-key.pem via OpenSSL.
    The output directory is Git-ignored (see .gitignore) — nothing here is
    ever committed. Re-running overwrites the existing local dev cert/key.

.EXAMPLE
    From the repo root:
        pwsh scripts/setup/generate-dev-tls-cert.ps1
    or in Windows PowerShell:
        powershell -File scripts/setup/generate-dev-tls-cert.ps1
#>

$ErrorActionPreference = "Stop"

$openssl = Get-Command openssl -ErrorAction SilentlyContinue
if (-not $openssl) {
    Write-Error @"
openssl was not found on PATH.
Install it (e.g. via Git for Windows, which bundles openssl.exe, or
'winget install ShiningLight.OpenSSL') and re-run this script.
"@
    exit 1
}

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$certDir = Join-Path $repoRoot "certs\local"
New-Item -ItemType Directory -Force -Path $certDir | Out-Null

$keyPath = Join-Path $certDir "dev-key.pem"
$certPath = Join-Path $certDir "dev-cert.pem"

Write-Host "Generating local self-signed TLS development certificate..."
Write-Host "  Key:  $keyPath"
Write-Host "  Cert: $certPath"

# Self-signed, 2048-bit RSA, 365-day validity, SAN covering localhost/127.0.0.1/::1
# so curl/browsers don't additionally complain about a hostname mismatch (they
# will still (correctly) warn about the self-signed/untrusted issuer — see
# docs/tls-in-transit.md for why that is expected and how to interpret it).
& openssl req -x509 -newkey rsa:2048 -sha256 -days 365 -nodes `
    -keyout $keyPath -out $certPath `
    -subj "/CN=localhost/O=Continuous KYC Autonomous Auditor (local dev only)" `
    -addext "subjectAltName=DNS:localhost,IP:127.0.0.1,IP:::1"

if ($LASTEXITCODE -ne 0) {
    Write-Error "openssl failed to generate the certificate (exit code $LASTEXITCODE)."
    exit $LASTEXITCODE
}

Write-Host ""
Write-Host "Done. This is a LOCAL DEVELOPMENT certificate only:"
Write-Host "  - self-signed (not issued by a trusted CA) -> clients will warn"
Write-Host "  - never commit certs/local/ (it is Git-ignored)"
Write-Host "  - production must use a certificate from a trusted CA / managed"
Write-Host "    load balancer / ACME workflow (see docs/tls-in-transit.md)"
Write-Host ""
Write-Host "Start the secure demonstration listener with:"
Write-Host "  python deployment/run_https_dev.py"
