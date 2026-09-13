@echo off
setlocal
cd /d "%~dp0"
python -m dds_companion.app %*
set EXITCODE=%ERRORLEVEL%
echo.
if not "%EXITCODE%"=="0" echo DDS Companion exited with code %EXITCODE%.
pause
exit /b %EXITCODE%
