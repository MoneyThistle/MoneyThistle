@echo off
rem Rebuilds MoneyThistle's Docker image from this folder and restarts the container
rem with it. Your data (data\) and backups (backups\) are kept.
rem A plain "restart" would keep running the old version; this picks up changes.
cd /d "%~dp0"
docker info >nul 2>&1
if errorlevel 1 (
  echo Docker isn't running. Start Docker Desktop, wait until it says it's running, then try again.
  pause
  exit /b 1
)
rem Stop a copy started without Docker, so both don't fight over port 8080.
python main.py --stop >nul 2>&1
rem Before the rename the container was called home-ledger: stop it (it backs up
rem first) and remove it, so it doesn't hold port 8080. Your data folder is kept.
docker inspect home-ledger >nul 2>&1
if not errorlevel 1 (
  echo Replacing the old home-ledger container with moneythistle ^(your data is kept^)...
  docker stop -t 60 home-ledger >nul
  docker rm home-ledger >nul
)
docker compose up -d --build --remove-orphans
if errorlevel 1 (
  pause
  exit /b 1
)
echo.
echo MoneyThistle is running in Docker: http://localhost:8080
timeout /t 5 >nul
