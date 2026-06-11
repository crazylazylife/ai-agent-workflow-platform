# Tear down the dev stack: stop the worker/API/web processes and the infra containers.
#   .\scripts\down.ps1
$root = Split-Path $PSScriptRoot -Parent

Write-Host "Stopping app servers (worker, API, web)..." -ForegroundColor Cyan
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -match 'uvicorn|celery' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
Get-CimInstance Win32_Process -Filter "Name='node.exe'" |
    Where-Object { $_.CommandLine -match 'next' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

Write-Host "Stopping infra containers..." -ForegroundColor Cyan
docker compose -f "$root\infra\docker-compose.yml" down

Write-Host "Down." -ForegroundColor Green
