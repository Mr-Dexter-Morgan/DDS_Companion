@echo off
setlocal
cd /d "%~dp0"
title DDS Companion 0.5.0

rem DDS Companion source/dev bootstrap: PySide6 is a required GUI component.
rem If it is missing, install it automatically without asking the user.
python -c "import PySide6" >nul 2>&1
if errorlevel 1 goto bootstrap_gui

goto launch_gui

:bootstrap_gui
cls
echo ============================================================
echo  DDS Companion 0.5.0 - Preparing application components
echo ============================================================
echo.
echo Required desktop components are missing and will be installed
echo automatically. No user action is required.
echo.
call install_gui_dependencies.bat --no-pause
if errorlevel 1 goto install_failed

rem Verify the dependency before attempting to launch the desktop UI.
python -c "import PySide6" >nul 2>&1
if errorlevel 1 goto install_failed

echo.
echo Components are ready. Starting DDS Companion...
timeout /t 1 /nobreak >nul

goto launch_gui

:launch_gui
for /f "usebackq delims=" %%P in (`python -c "import pathlib,sys; print(pathlib.Path(sys.executable).with_name('pythonw.exe'))"`) do set "PYTHONW=%%P"
if not exist "%PYTHONW%" goto no_pythonw
start "" "%PYTHONW%" "%~dp0run_companion.pyw" %*
exit /b 0

:install_failed
echo.
echo ============================================================
echo  DDS Companion could not prepare the desktop components.
echo ============================================================
echo Check the network connection and Python installation, then run
echo run_companion.bat again. No DDS archive data was changed.
echo.
pause
exit /b 4

:no_pythonw
echo.
echo pythonw.exe was not found next to the active Python interpreter.
echo Use run_companion_debug.bat and check your Python installation.
pause
exit /b 5
