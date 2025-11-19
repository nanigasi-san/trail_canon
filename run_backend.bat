@echo off
setlocal
cd /d "%~dp0backend"
echo [TrailDetector] Installing backend dependencies with uv...
uv sync
if errorlevel 1 (
    echo Failed to install backend dependencies.
    exit /b 1
)
echo [TrailDetector] Starting FastAPI server on http://127.0.0.1:8000
uv run uvicorn app.main:app --reload
