@echo off
cd /d "%~dp0backend"
echo Installing dependencies...
python -m pip install -r requirements.txt
echo Starting Equity Signal Engine...
python -m app.main
pause
