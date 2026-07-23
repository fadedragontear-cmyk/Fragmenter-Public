@echo off
setlocal EnableExtensions
cd /d "%~dp0\.."

echo Fragmenter 1.0 current-release validation
echo ===========================================
echo.

where py >nul 2>nul
if errorlevel 1 (
  echo Python 3 with the Windows py launcher was not found.
  pause
  exit /b 1
)

py -3 -c "import pytest; import tkinter" >nul 2>nul
if errorlevel 1 (
  echo Pytest and Tkinter are required for source validation.
  echo Install pytest with: py -3 -m pip install pytest
  pause
  exit /b 1
)

py -3 -m py_compile ^
  fragmenter_public.py ^
  tools\fragmenter_public_gui_v127.py ^
  tools\fragmenter_public_gui_v126.py ^
  tools\fragmenter_public_gui_v125.py ^
  tools\fragment_4_builder_v127.py ^
  tools\tellipatch_resource_v122.py ^
  tools\netslum_completion_v124.py ^
  tools\run_all_executor_v9.py ^
  tools\build_fragmenter_release.py
if errorlevel 1 goto :failed

py -3 -m pytest -q ^
  tests\test_fragmenter_current_release.py ^
  tests\test_frozen_run_all_release.py
if errorlevel 1 goto :failed

echo.
echo Fragmenter 1.0 current-release validation passed.
pause
exit /b 0

:failed
echo.
echo Fragmenter 1.0 current-release validation failed. Review the output above.
pause
exit /b 1
