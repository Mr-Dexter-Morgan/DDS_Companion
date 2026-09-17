@echo off
setlocal
cd /d "%~dp0"
title DDS Companion 0.5.0 - One-shot import
python -m dds_companion.app --once %*
set EXITCODE=%ERRORLEVEL%
echo.
if not "%EXITCODE%"=="0" echo DDS Companion exited with code %EXITCODE%.
pause
exit /b %EXITCODE%
