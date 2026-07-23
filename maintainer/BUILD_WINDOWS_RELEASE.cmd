@echo off
setlocal EnableExtensions
cd /d "%~dp0\.."

echo Fragmenter 1.0 Windows release build
echo =====================================
echo.

where py >nul 2>nul
if errorlevel 1 (
  echo Python 3 with the Windows py launcher was not found.
  pause
  exit /b 1
)

where dotnet >nul 2>nul
if errorlevel 1 (
  echo The .NET 8 SDK is required to build the bundled ISO bridge.
  echo End users do not need .NET.
  pause
  exit /b 1
)

py -3 -c "import PyInstaller" >nul 2>nul
if errorlevel 1 (
  echo PyInstaller is required.
  echo Install it with: py -3 -m pip install --upgrade pyinstaller
  pause
  exit /b 1
)

py -3 tools\build_fragmenter_release.py
if errorlevel 1 (
  echo.
  echo Fragmenter release build failed.
  pause
  exit /b 1
)

echo.
echo Fragmenter.exe and the Windows x64 ZIP are ready under dist\.
echo The executable uses assets\branding\Fragmenter.ico.
pause
exit /b 0
