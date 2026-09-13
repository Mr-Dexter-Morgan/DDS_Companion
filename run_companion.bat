@echo off
setlocal
cd /d "%~dp0"
title DDS Companion 0.4.1

python -c "import PySide6" >nul 2>&1
if errorlevel 1 goto missing_gui

for /f "usebackq delims=" %%P in (`python -c "import pathlib,sys; print(pathlib.Path(sys.executable).with_name('pythonw.exe'))"`) do set "PYTHONW=%%P"
if not exist "%PYTHONW%" goto no_pythonw
start "" "%PYTHONW%" "%~dp0run_companion.pyw" %*
exit /b 0

:missing_gui
echo.
echo DDS Companion 0.4.1 GUI dependency PySide6 is not installed.
echo.
choice /C YN /N /M "Install it now? [Y/N]: "
if errorlevel 2 exit /b 4
call install_gui_dependencies.bat --no-pause
if errorlevel 1 exit /b %ERRORLEVEL%
goto launch_after_install

:launch_after_install
for /f "usebackq delims=" %%P in (`python -c "import pathlib,sys; print(pathlib.Path(sys.executable).with_name('pythonw.exe'))"`) do set "PYTHONW=%%P"
if not exist "%PYTHONW%" goto no_pythonw
start "" "%PYTHONW%" "%~dp0run_companion.pyw" %*
exit /b 0

:no_pythonw
echo.
echo pythonw.exe was not found next to the active Python interpreter.
echo Use run_companion_debug.bat and check your Python installation.
pause
exit /b 5
