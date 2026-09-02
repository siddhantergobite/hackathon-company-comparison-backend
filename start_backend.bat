@echo off
chcp 65001 >nul
echo === Casefile (the only UI) — port 8765 ===
echo.
echo   Open this every time:
echo   http://127.0.0.1:8765/casefile/
echo.
echo   Do NOT use localhost:3000 — that was an old/other tab
echo   and it is why AEO/GEO looked missing last time.
echo.
cd /d "%~dp0"
set PYTHONPATH=%~dp0
set PYTHONIOENCODING=utf-8
echo Working dir: %CD%
echo Using .env at: %CD%\.env
echo.
REM Open the Casefile UI once the server is up
start "" cmd /c "timeout /t 4 /nobreak >nul && start http://127.0.0.1:8765/casefile/"
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8765 --reload
pause
