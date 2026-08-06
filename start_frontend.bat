@echo off
title Agent Pipeline — Frontend
echo Starting Vite dev server on http://localhost:5173 ...
cd /d "%~dp0frontend"
node -e "require('child_process').execSync('npm run dev', {stdio: 'inherit', cwd: process.cwd()})"
pause
