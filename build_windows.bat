@echo off
setlocal
cd /d "%~dp0"

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

if exist build\pyinstaller rmdir /s /q build\pyinstaller
if exist dist\DDS rmdir /s /q dist\DDS

python -m PyInstaller --noconfirm --clean --workpath build\pyinstaller --distpath dist DDS.spec
if errorlevel 1 exit /b 7

if not exist "dist\DDS\DDS.exe" (
  echo [DDS] Build finished without dist\DDS\DDS.exe
  exit /b 8
)

echo.
echo [DDS] Windows onedir build ready:
echo       %CD%\dist\DDS\DDS.exe
exit /b 0
