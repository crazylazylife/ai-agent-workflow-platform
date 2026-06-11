# One-command dev bring-up for the AI Agent Workflow Platform (Windows).
#   .\scripts\dev.ps1
# Starts infra, runs migrations, then launches the worker, API, and web dashboard
# each in its own window. Stop everything with .\scripts\down.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$venv = Join-Path $root ".venv\Scripts"
$py = Join-Path $venv "python.exe"

Write-Host "[1/4] Starting infra (Postgres, Redis, Jaeger)..." -ForegroundColor Cyan
docker compose -f "$root\infra\docker-compose.yml" --env-file "$root\.env" up -d

Write-Host "[2/4] Waiting for Postgres to be healthy..." -ForegroundColor Cyan
$status = ""
for ($i = 0; $i -lt 30; $i++) {
    $status = docker inspect -f '{{.State.Health.Status}}' awp-postgres 2>$null
    if ($status -eq 'healthy') { break }
    Start-Sleep -Seconds 2
}
if ($status -ne 'healthy') { Write-Host "Postgres did not become healthy; aborting." -ForegroundColor Red; exit 1 }

Write-Host "[3/4] Applying database migrations..." -ForegroundColor Cyan
Push-Location "$root\packages\shared"
& "$venv\alembic.exe" upgrade head
Pop-Location

Write-Host "[4/4] Launching worker, API, and web (separate windows)..." -ForegroundColor Cyan
# $root and $py expand now; `$env stays literal for the child shell.
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root\apps\worker'; `$env:PYTHONPATH='.'; & '$py' -m celery -A celery_app worker --pool=solo --loglevel=info"
# beat must run as its own process on Windows (it can't be embedded with -B). Drives the resume sweeper.
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root\apps\worker'; `$env:PYTHONPATH='.'; & '$py' -m celery -A celery_app beat --loglevel=info"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root\apps\api'; `$env:PYTHONPATH='.'; & '$py' -m uvicorn main:app --reload --port 8000"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root\apps\web'; npm run dev"

Write-Host ""
Write-Host "Up! Dashboard http://localhost:3000  |  API docs http://localhost:8000/docs  |  Jaeger http://localhost:16686" -ForegroundColor Green
Write-Host "Stop everything: .\scripts\down.ps1" -ForegroundColor Yellow
