@echo off
setlocal
cd /d "%~dp0"
title DDS Companion - GUI dependency installer
set NOPAUSE=0
if /I "%~1"=="--no-pause" set NOPAUSE=1

echo DDS Companion needs PySide6 for the desktop interface.
echo This installer uses the active Python environment.
echo.
python --version
if errorlevel 1 (
  echo.
  echo Python was not found in PATH.
  if "%NOPAUSE%"=="0" pause
  exit /b 2
)

echo.
python -m pip install --upgrade -r requirements-gui.txt
set EXITCODE=%ERRORLEVEL%
echo.
if "%EXITCODE%"=="0" (
  echo PySide6 is ready.
) else (
  echo Installation failed with code %EXITCODE%.
  echo No DDS archive data was changed.
)
if "%NOPAUSE%"=="0" pause
exit /b %EXITCODE%
