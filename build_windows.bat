@echo off
setlocal
cd /d "%~dp0"

if "%DDS_BUILD_LOCK_HELD%"=="1" goto :locked_build
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\run_locked_build.ps1" "%~f0"
exit /b %errorlevel%

:locked_build
where py >nul 2>nul
if errorlevel 1 (
  echo [DDS] Python launcher ^(py^) not found.
  exit /b 2
)

if not exist ".venv-build\Scripts\python.exe" (
  echo [DDS] Creating isolated build environment...
  py -3 -m venv .venv-build || exit /b 3
)

call ".venv-build\Scripts\activate.bat" || exit /b 4
python -m pip install --upgrade pip || exit /b 5
python -m pip install -r requirements-build.txt || exit /b 6

python tools\prepare_windows_build.py
if errorlevel 1 exit /b 15

python tools\generate_windows_version_info.py
if errorlevel 1 exit /b 14

python -m PyInstaller --noconfirm --clean --workpath build\pyinstaller-app --distpath build\artifacts\app DDSApp.spec
if errorlevel 1 exit /b 7

python -m PyInstaller --noconfirm --clean --workpath build\pyinstaller-launcher --distpath build\artifacts\bootstrap DDSLauncher.spec
if errorlevel 1 exit /b 8

python -m PyInstaller --noconfirm --clean --workpath build\pyinstaller-updater --distpath build\artifacts\bootstrap DDSUpdater.spec
if errorlevel 1 exit /b 9

python tools\assemble_windows_dist.py
if errorlevel 1 exit /b 10

if not exist "dist\DDS\DDS.exe" exit /b 11
if not exist "dist\DDS\DDSUpdater.exe" exit /b 12
if not exist "dist\DDS\current.json" exit /b 13

echo.
echo [DDS] Versioned Windows distribution ready:
echo       %CD%\dist\DDS\DDS.exe
exit /b 0
