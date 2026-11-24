@echo off
rem Stops MoneyThistle (it makes its after-changes backup first).
cd /d "%~dp0"
python main.py --stop
timeout /t 3 >nul
