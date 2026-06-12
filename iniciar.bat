@echo off
rem Radar de Pregoes - inicia backend (8000) + frontend (5173) em duas janelas
rem e abre o navegador. Feche as janelas para parar os servidores.
cd /d "%~dp0"
start "Radar API (8000)" cmd /k "cd backend && .venv\Scripts\python -m uvicorn app.main:app --port 8000 --reload"
start "Radar UI (5173)" cmd /k "cd frontend && npm run dev"
timeout /t 4 >nul
start http://localhost:5173
