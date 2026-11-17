@echo off
rem ------------------------------------------------------------------
rem MyIssueDesk installer launcher.
rem Finds Python 3.11 or newer and runs installer.py with the same
rem arguments:  install.cmd --target C:\Utility\MyIssueDesk
rem             install.cmd --check          (show what would be done)
rem ------------------------------------------------------------------
setlocal EnableExtensions
set "PY="
for %%V in (3.13 3.12 3.11) do if not defined PY (py -%%V -c "import sys" >nul 2>&1 && set "PY=py -%%V")
if not defined PY python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1 && set "PY=python"
if not defined PY (
  echo Python 3.11 or newer was not found. Install it from python.org and run this again.
  exit /b 2
)
%PY% "%~dp0installer.py" %*
exit /b %ERRORLEVEL%
