@echo off
setlocal
cd /d "%~dp0"
title DDS Companion 0.5.7 DEBUG
python -m dds_companion.gui.app %*
set EXITCODE=%ERRORLEVEL%
echo.
echo DDS Companion debug session exited with code %EXITCODE%.
pause
exit /b %EXITCODE%
