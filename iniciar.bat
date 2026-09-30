@echo off
REM Windows: instala as dependencias (na primeira vez) e inicia o sistema.
cd /d "%~dp0"
if not exist .venv (py -3 -m venv .venv)
.venv\Scripts\pip install -q -r requirements.txt
start "" http://localhost:8000
.venv\Scripts\python run.py
pause
