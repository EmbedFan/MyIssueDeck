@echo off
rem ------------------------------------------------------------------
rem MyIssueDesk installer
rem
rem Installs the myissuedeck wheel into C:\Utility\MyIssueDesk with a
rem virtual environment in .venv, and copies the current data, settings
rem and project files from the source checkout. It does not stop or
rem change any server that is already running.
rem
rem Run it from anywhere:  installer\install-myissuedesk.cmd
rem Requires Python 3.11 or newer and internet access for the libraries.
rem ------------------------------------------------------------------
setlocal EnableExtensions

set "VERSION=0.9.0"
set "TARGET=C:\Utility\MyIssueDesk"
set "SRC=%~dp0.."
for %%I in ("%SRC%") do set "SRC=%%~fI"
set "WHEEL=%SRC%\dist\myissuedeck-%VERSION%-py3-none-any.whl"
set "VENV_PY=%TARGET%\.venv\Scripts\python.exe"

echo.
echo MyIssueDesk %VERSION% installer
echo   source: %SRC%
echo   target: %TARGET%
echo.

if not exist "%WHEEL%" (
  echo The wheel was not found: %WHEEL%
  echo Build it first: open the project folder and run  .venv\Scripts\uv.exe build
  exit /b 1
)

set "PY_CMD="
py -3.11 -c "import sys" >nul 2>&1 && set "PY_CMD=py -3.11"
if not defined PY_CMD python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1 && set "PY_CMD=python"
if not defined PY_CMD (
  echo Python 3.11 or newer was not found. Install it from python.org and run this again.
  exit /b 1
)
echo Using Python: %PY_CMD%
echo.

echo [1/6] Creating folders
if not exist "%TARGET%" mkdir "%TARGET%"
if not exist "%TARGET%\dist" mkdir "%TARGET%\dist"
if not exist "%TARGET%\data" mkdir "%TARGET%\data"
if not exist "%TARGET%\projects" mkdir "%TARGET%\projects"
if not exist "%TARGET%\logs" mkdir "%TARGET%\logs"
if not exist "%TARGET%\run" mkdir "%TARGET%\run"

echo [2/6] Copying the wheel
copy /y "%WHEEL%" "%TARGET%\dist\" >nul
if errorlevel 1 exit /b 1

echo [3/6] Creating the virtual environment (.venv)
if not exist "%VENV_PY%" %PY_CMD% -m venv "%TARGET%\.venv"
if errorlevel 1 exit /b 1

echo [4/6] Installing MyIssueDesk and its libraries
set "UV=%SRC%\.venv\Scripts\uv.exe"
if exist "%UV%" (
  rem uv with the Windows certificate store, as the project notes require on this PC.
  "%UV%" pip install --system-certs --python "%VENV_PY%" "%TARGET%\dist\myissuedeck-%VERSION%-py3-none-any.whl"
) else (
  "%VENV_PY%" -m pip install --retries 10 --timeout 120 "%TARGET%\dist\myissuedeck-%VERSION%-py3-none-any.whl"
)
if errorlevel 1 (
  echo The installation failed. Check the internet connection and the messages above.
  exit /b 1
)

echo [5/6] Copying the data, settings and projects
rem The tracker database is copied with SQLite's backup API: it is in WAL mode
rem and may be in use, so a plain file copy could be inconsistent.
"%VENV_PY%" -c "import sqlite3,sys; src=sqlite3.connect(sys.argv[1]); dst=sqlite3.connect(sys.argv[2]); src.backup(dst); dst.close(); src.close()" "%SRC%\data\tracker.db" "%TARGET%\data\tracker.db"
if errorlevel 1 (
  echo Could not copy the tracker database.
  exit /b 1
)
robocopy "%SRC%\data" "%TARGET%\data" /E /XF "%SRC%\data\tracker.db" "%SRC%\data\tracker.db-wal" "%SRC%\data\tracker.db-shm" >nul
if errorlevel 8 (
  echo Could not copy the data folder.
  exit /b 1
)
copy /y "%SRC%\server.toml" "%TARGET%\server.toml" >nul
if errorlevel 1 (
  echo Could not copy server.toml.
  exit /b 1
)
robocopy "%SRC%\projects" "%TARGET%\projects" /E /XF "%SRC%\projects\.mcp.json" >nul
if errorlevel 8 (
  echo Could not copy the projects folder.
  exit /b 1
)
if exist "%SRC%\project-templates" robocopy "%SRC%\project-templates" "%TARGET%\project-templates" /E >nul

echo [6/6] Installing the start and stop scripts
copy /y "%~dp0start-myissuedesk.vbs" "%TARGET%\" >nul
copy /y "%~dp0stop-myissuedesk.vbs" "%TARGET%\" >nul
copy /y "%~dp0start-server.ps1" "%TARGET%\" >nul
copy /y "%~dp0stop-server.ps1" "%TARGET%\" >nul

echo.
"%TARGET%\.venv\Scripts\issuedeck.exe" --version
if errorlevel 1 (
  echo The installed command did not run.
  exit /b 1
)
echo.
echo Installed to %TARGET%.
echo Start the server with  %TARGET%\start-myissuedesk.vbs
echo Stop the server with   %TARGET%\stop-myissuedesk.vbs
echo.
endlocal
exit /b 0
