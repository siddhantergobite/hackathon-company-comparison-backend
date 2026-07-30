@echo off
chcp 65001 >nul
echo === AI Creative Studio Backend (port 8765) ===
cd /d "c:\Users\admin\Desktop\Hackathon"
set PYTHONPATH=c:\Users\admin\Desktop\Hackathon
set PYTHONIOENCODING=utf-8
echo Starting on http://localhost:8765
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8765 --reload
pause
