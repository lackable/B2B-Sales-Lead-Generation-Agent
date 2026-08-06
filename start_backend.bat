@echo off
title Agent Pipeline — Backend
echo Starting FastAPI backend on http://localhost:8000 ...
cd /d "%~dp0backend"
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
pause
