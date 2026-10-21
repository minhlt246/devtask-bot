# Start DevTask Bot on Windows in the background/service mode with logging.
# Usage:
#   powershell -ExecutionPolicy Bypass -File .\scripts\start_bot.ps1

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$LogDir = Join-Path $ProjectRoot "data\logs"

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

if (-not (Test-Path $Python)) {
    throw "Python virtual environment not found: $Python. Please run: python -m venv .venv; .venv\Scripts\pip install -r requirements.txt"
}

Set-Location $ProjectRoot

& $Python -m app.main `
    1>> (Join-Path $LogDir "bot.stdout.log") `
    2>> (Join-Path $LogDir "bot.stderr.log")

exit $LASTEXITCODE
