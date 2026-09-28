@echo off
title Agent Pipeline — Backend
echo Starting FastAPI backend on http://localhost:8000 ...
cd /d "%~dp0"
set "PY=python"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
"%PY%" -m uvicorn leadgen.api.app:app --host 0.0.0.0 --port 8000 --reload
pause
