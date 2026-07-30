@echo off
chcp 65001 >nul
echo === AI Creative Studio Frontend ===
cd /d "c:\Users\admin\Desktop\Hackathon"
set PYTHONIOENCODING=utf-8
REM API keys: set in .env (see .env.example)

REM Kill existing Streamlit on port 8501
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| find ":8501 " ^| find "LISTENING"') do (
    taskkill /F /PID %%a 2>nul
)
timeout /t 1 /nobreak >nul

echo Starting Streamlit frontend on http://localhost:8501
streamlit run app.py --server.port 8501
pause
