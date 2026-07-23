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

rem The supported no-admin SDK install lives under %%USERPROFILE%%\.dotnet.
rem Prefer it over a runtime-only C:\Program Files\dotnet entry left earlier in PATH.
set "USER_DOTNET_ROOT=%USERPROFILE%\.dotnet"
if exist "%USER_DOTNET_ROOT%\dotnet.exe" (
  "%USER_DOTNET_ROOT%\dotnet.exe" --list-sdks 2>nul | findstr /b /c:"8.0." >nul
  if not errorlevel 1 (
    set "DOTNET_ROOT=%USER_DOTNET_ROOT%"
    set "PATH=%USER_DOTNET_ROOT%;%PATH%"
  )
)

set "DOTNET_EXE="
for /f "delims=" %%D in ('where dotnet 2^>nul') do if not defined DOTNET_EXE set "DOTNET_EXE=%%D"
if not defined DOTNET_EXE (
  echo The .NET 8 SDK is required to build the bundled ISO bridge.
  echo End users do not need .NET.
  pause
  exit /b 1
)

"%DOTNET_EXE%" --list-sdks 2>nul | findstr /b /c:"8.0." >nul
if errorlevel 1 (
  echo A dotnet runtime was found, but no .NET 8 SDK is available to this shell.
  echo Current dotnet: %DOTNET_EXE%
  echo Expected user SDK: %USER_DOTNET_ROOT%\dotnet.exe
  pause
  exit /b 1
)

echo Using .NET SDK: %DOTNET_EXE%

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
