# Set error action preference
$ErrorActionPreference = "Continue"

# 1. Check for virtual environment and activate it
if (Test-Path ".\.venv\Scripts\Activate.ps1") {
    Write-Host "Activating virtual environment (.venv)..." -ForegroundColor Cyan
    . .\.venv\Scripts\Activate.ps1
} elseif (Test-Path ".\venv\Scripts\Activate.ps1") {
    Write-Host "Activating virtual environment (venv)..." -ForegroundColor Cyan
    . .\venv\Scripts\Activate.ps1
} else {
    Write-Host "No local virtual environment found, running with system Python." -ForegroundColor Yellow
}

# 2. Check if uvicorn is installed
$hasUvicorn = $false
try {
    python -c "import uvicorn" 2>$null
    if ($LASTEXITCODE -eq 0) {
        $hasUvicorn = $true
    }
} catch {}

if (-not $hasUvicorn) {
    Write-Host "uvicorn is not installed! Installing requirements..." -ForegroundColor Yellow
    pip install -r requirements.txt
}

# 3. Start the server
Write-Host "Starting FastAPI / Uvicorn server on http://127.0.0.1:8000..." -ForegroundColor Green
python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
