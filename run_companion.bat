@echo off
setlocal
cd /d "%~dp0"
title DDS Companion 0.4.0

python -c "import PySide6" >nul 2>&1
if errorlevel 1 goto missing_gui

python -m dds_companion.gui.app %*
set EXITCODE=%ERRORLEVEL%
if not "%EXITCODE%"=="0" (
  echo.
  echo DDS Companion GUI exited with code %EXITCODE%.
  pause
)
exit /b %EXITCODE%

:missing_gui
echo.
echo DDS Companion 0.4.0 GUI dependency PySide6 is not installed.
echo.
choice /C YN /N /M "Install it now? [Y/N]: "
if errorlevel 2 exit /b 4
call install_gui_dependencies.bat --no-pause
if errorlevel 1 exit /b %ERRORLEVEL%
python -m dds_companion.gui.app %*
set EXITCODE=%ERRORLEVEL%
if not "%EXITCODE%"=="0" pause
exit /b %EXITCODE%
