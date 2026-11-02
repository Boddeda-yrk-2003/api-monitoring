@echo off
REM APIGuard - start backend (FastAPI :8000) and frontend (React :5173)
setlocal
set ROOT=%~dp0

echo ==^> Backend (FastAPI)
cd /d "%ROOT%backend"
if not exist ".venv" (
    echo     creating virtual environment...
    python -m venv .venv
)
call .venv\Scripts\activate.bat
pip install -q -r requirements.txt
start "APIGuard Backend" cmd /c "python -m uvicorn app.main:app --host 0.0.0.0 --port 8000"

echo ==^> Frontend (React)
cd /d "%ROOT%frontend"
if not exist "node_modules" (
    echo     installing npm packages (first run)...
    call npm install --no-audit --no-fund
)
start "APIGuard Frontend" cmd /c "npm run dev"

echo.
echo   Dashboard : http://localhost:5173
echo   API docs  : http://localhost:8000/docs
echo   Metrics   : http://localhost:8000/metrics
echo.
echo Two new windows were opened - close them to stop the services.
endlocal
