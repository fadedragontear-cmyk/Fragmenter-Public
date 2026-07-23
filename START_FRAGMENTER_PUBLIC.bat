@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "MISSING=0"
for %%F in (
  "fragmenter_public.py"
  "tools\fragmenter_public_gui_v127.py"
  "tools\fragmenter_public_gui_v126.py"
  "tools\fragmenter_public_gui_v125.py"
  "tools\netslum_completion_v124.py"
  "assets\branding\Fragmenter-Serenial.png"
  "resources\Fragment-Network.ps2.gz"
  "resources\Tellipatch-gamelines.csv.gz"
  "resources\game_setup\Fragment-4.0-completion.zip.b64"
  "resources\game_setup\Tellipatch-v3.8-patches.zip.rawpart2.b64"
  "resources\game_setup\Tellipatch-v3.8-patches.zip.rawpart1.b64"
) do (
  if not exist "%%~F" (
    echo Missing required file: %%~F
    set "MISSING=1"
  )
)
if "%MISSING%"=="1" (
  echo.
  echo This checkout is incomplete. Run: git pull --ff-only
  pause
  exit /b 1
)

where py >nul 2>nul
if errorlevel 1 (
  echo Fragmenter requires Python 3 with the Windows py launcher.
  echo Install Python 3, enable the py launcher, then run this file again.
  pause
  exit /b 1
)

py -3 -c "import tkinter; import sys; print('Fragmenter Python', sys.version.split()[0], '- Tk available')"
if errorlevel 1 (
  echo Python is installed, but Tkinter is unavailable.
  pause
  exit /b 1
)

py -3 fragmenter_public.py
set EXIT_CODE=%ERRORLEVEL%
if not "%EXIT_CODE%"=="0" (
  echo.
  echo Fragmenter exited with code %EXIT_CODE%.
  echo Run git pull --ff-only if the traceback reports a missing repository file.
  pause
)
exit /b %EXIT_CODE%
