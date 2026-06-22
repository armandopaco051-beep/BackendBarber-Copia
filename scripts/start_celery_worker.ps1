$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

$python = Join-Path $projectRoot "venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Host "No se encontro el venv en $python"
    exit 1
}

& $python -m celery -A barberia worker -l info -P solo
