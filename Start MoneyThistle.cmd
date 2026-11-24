@echo off
rem Starts MoneyThistle in the background and opens it in your browser.
rem It keeps running after this window closes; use "Stop MoneyThistle" to stop it.
cd /d "%~dp0"
python main.py --background %*
if errorlevel 1 (
  echo.
  echo Something went wrong. Details are in moneythistle.log, in the folder named above.
  pause
)
