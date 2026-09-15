@echo off
setlocal
cd /d "%~dp0"
title DDS Companion 0.4.4 - CLI
python -m dds_companion.app %*
set EXITCODE=%ERRORLEVEL%
echo.
if not "%EXITCODE%"=="0" echo DDS Companion CLI exited with code %EXITCODE%.
pause
exit /b %EXITCODE%
