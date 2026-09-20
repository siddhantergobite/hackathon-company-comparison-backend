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
REM Build the React UI on first run (needs Node.js); otherwise the legacy UI is served
if exist "frontend\dist\index.html" goto start
where npm >nul 2>nul
if errorlevel 1 (
  echo [warn] Node.js not found - serving the legacy UI. Install Node.js to use the React UI.
  goto start
)
echo Building the React UI ^(first run only^)...
pushd frontend
call npm install
call npm run build
popd
echo.

:start
REM Open the Casefile UI once the server is up
start "" cmd /c "timeout /t 4 /nobreak >nul && start http://127.0.0.1:8765/casefile/"
REM Prefer the project venv (its packages are installed there). "python -m uvicorn" is used instead of
REM uvicorn.exe because some machines block .exe launchers via Device Guard.
set "PY=python"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
"%PY%" -m uvicorn backend.main:app --host 0.0.0.0 --port 8765 --reload
pause
