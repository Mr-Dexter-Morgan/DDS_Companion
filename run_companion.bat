@echo off
setlocal
cd /d "%~dp0"
title DDS Companion 0.3.0 - Activity and Health Core
python -m dds_companion.app %*
set EXITCODE=%ERRORLEVEL%
echo.
if not "%EXITCODE%"=="0" echo DDS Companion exited with code %EXITCODE%.
pause
exit /b %EXITCODE%
