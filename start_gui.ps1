# Start Subtitle Translator GUI (venv Version)
$ErrorActionPreference = "Stop"
$BASE_DIR = $PSScriptRoot
if (-not $BASE_DIR) { $BASE_DIR = Get-Location }
$PYTHON_ENV = Join-Path $BASE_DIR "python_env"
$VENV_PYTHON = Join-Path $PYTHON_ENV "Scripts\python.exe"

if (-not (Test-Path -LiteralPath "$VENV_PYTHON")) {
    Write-Host "Error: Virtual environment not found. Please run 'setup_project.ps1' first." -ForegroundColor "Red"
    Pause
    exit 1
}

Write-Host "Starting GUI (Isolated venv)..." -ForegroundColor "Green"
& "$VENV_PYTHON" "subtitle/main.py"
