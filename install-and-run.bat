@echo off
rem Raval Trips - Windows: double-click this file. First run installs, later runs just start the app.
cd /d "%~dp0"
where py >nul 2>nul && (set PY=py -3) || (set PY=python)
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>nul
if errorlevel 1 (
  echo Python 3.10 or newer is required. Install it from https://www.python.org/downloads/ ^(tick "Add python.exe to PATH"^) and run this again.
  pause
  exit /b 1
)
if not exist .venv\Scripts\raval-trips.exe (
  echo Installing Raval Trips ^(one time, about a minute^)...
  %PY% -m venv .venv
  .venv\Scripts\python -m pip install --quiet --upgrade pip
  .venv\Scripts\python -m pip install --quiet .
  if errorlevel 1 ( echo Installation failed. & pause & exit /b 1 )
)
.venv\Scripts\raval-trips.exe serve
pause
