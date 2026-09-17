@echo off
setlocal
cd /d "%~dp0"
title DDS Companion - Preparing application components
set NOPAUSE=0
if /I "%~1"=="--no-pause" set NOPAUSE=1

echo DDS Companion is preparing required desktop components.
echo This may take a few minutes on the first launch.
echo.
python --version
if errorlevel 1 (
  echo.
  echo Python was not found in PATH.
  if "%NOPAUSE%"=="0" pause
  exit /b 2
)

echo.
rem Do not use --upgrade here: on bootstrap we only need to satisfy the
rem pinned/compatible requirement, not churn an already valid environment.
python -m pip install --disable-pip-version-check -r requirements-gui.txt
set EXITCODE=%ERRORLEVEL%
echo.
if "%EXITCODE%"=="0" (
  echo Required desktop components are ready.
) else (
  echo Component installation failed with code %EXITCODE%.
  echo No DDS archive data was changed.
)
if "%NOPAUSE%"=="0" pause
exit /b %EXITCODE%
