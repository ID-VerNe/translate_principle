# Subtitle Translator Setup Script (Windows venv Version)
$ErrorActionPreference = "Stop"

# Get script root safely
$BASE_DIR = $PSScriptRoot
if (-not $BASE_DIR) { $BASE_DIR = Get-Location }

$PYTHON_ENV = Join-Path $BASE_DIR "python_env"
$SUBTITLE_DIR = Join-Path $BASE_DIR "subtitle"
$VENV_PYTHON = Join-Path $PYTHON_ENV "Scripts\python.exe"

Write-Host "=== Subtitle Translator Automation Deployment (Windows) ===" -ForegroundColor "Cyan"

# 1. Check for System Python
if (-not (Get-Command "python" -ErrorAction SilentlyContinue)) {
    Write-Host "Error: Python not found in PATH. Please install Python 3.10+ first." -ForegroundColor "Red"
    Pause
    exit 1
}

# 2. Check and Install Chocolatey & MKVToolNix
if (-not (Get-Command "choco" -ErrorAction SilentlyContinue)) {
    Write-Host "Chocolatey not found. Installing..." -ForegroundColor "Yellow"
    Set-ExecutionPolicy Bypass -Scope Process -Force
    [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
    $url = "https://community.chocolatey.org/install.ps1"
    $install_script = (New-Object System.Net.WebClient).DownloadString($url)
    Invoke-Expression $install_script
}
if (-not (Get-Command "mkvmerge" -ErrorAction SilentlyContinue)) {
    Write-Host "Installing MKVToolNix via Chocolatey..." -ForegroundColor "Cyan"
    & choco install mkvtoolnix -y
}

# 3. Create Virtual Environment (venv)
if (-not (Test-Path -LiteralPath $PYTHON_ENV)) {
    Write-Host "Step 3: Creating virtual environment in $PYTHON_ENV..." -ForegroundColor "Cyan"
    # This inherits Tkinter from your system Python automatically
    python -m venv $PYTHON_ENV
}

# 4. Install Dependencies into venv
Write-Host "Step 4: Installing project dependencies (TUNA Mirror)..." -ForegroundColor "Cyan"
& "$VENV_PYTHON" -m pip install --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple
& "$VENV_PYTHON" -m pip install -r "$SUBTITLE_DIR\requirements.txt" -i https://pypi.tuna.tsinghua.edu.cn/simple

# 5. .env Initialization
$DOT_ENV = Join-Path $SUBTITLE_DIR ".env"
$DOT_ENV_EX = Join-Path $SUBTITLE_DIR ".env.example"
if (-not (Test-Path -LiteralPath $DOT_ENV)) {
    if (Test-Path -LiteralPath $DOT_ENV_EX) {
        Copy-Item -LiteralPath $DOT_ENV_EX -Destination $DOT_ENV -Force
        Write-Host "Created .env, please remember to fill in your API key." -ForegroundColor "Yellow"
    }
}

Write-Host "=======================================================" -ForegroundColor "Green"
Write-Host "Deployment Completed Successfully!" -ForegroundColor "Green"
Write-Host "Using virtual environment for perfect isolation." -ForegroundColor "Cyan"
Write-Host "You can now run 'start_gui.ps1' to start the program." -ForegroundColor "Green"
Write-Host "=======================================================" -ForegroundColor "Green"