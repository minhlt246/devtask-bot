# Start DevTask Bot on Windows (PowerShell).
# Usage (from repo root):
#   powershell -ExecutionPolicy Bypass -File .\scripts\run_bot.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    Write-Error "Virtual environment not found. Create it with: python -m venv .venv"
}

& $VenvPython -m app.main
