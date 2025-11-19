@echo off
setlocal
cd /d "%~dp0frontend"
echo [TrailDetector] Installing frontend dependencies with npm...
npm install
if errorlevel 1 (
    echo Failed to install frontend dependencies.
    exit /b 1
)
echo [TrailDetector] Starting Vite dev server on http://127.0.0.1:5173
npm run dev
