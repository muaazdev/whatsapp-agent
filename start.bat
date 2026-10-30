@echo off
cd /d "%~dp0"
if not exist .env (
  copy .env.example .env >nul
  echo Created .env - paste your keys in Notepad, save, close it, then double-click start.bat again.
  notepad .env
  exit /b
)
python -m pip install -q -r requirements.txt
python agent.py
pause
