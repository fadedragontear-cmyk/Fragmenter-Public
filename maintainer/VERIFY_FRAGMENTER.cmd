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
  tools\run_all_cancellation_v1.py ^
  tools\run_all_cancel_ui_v1.py ^
  tools\fragmenter_release_experience_v1.py ^
  tools\fragmenter_visual_runtime_v6.py ^
  tools\ccsf_textured_scene_v9.py ^
  tools\ccsf_textured_renderer_v5.py ^
  tools\build_fragmenter_release.py
if errorlevel 1 goto :failed

set "PYTEST_BASETEMP=%CD%\build\pytest-current-release"
if exist "%PYTEST_BASETEMP%" rmdir /s /q "%PYTEST_BASETEMP%"
mkdir "%PYTEST_BASETEMP%" >nul 2>nul
if errorlevel 1 (
  echo Could not create the local pytest workspace:
  echo %PYTEST_BASETEMP%
  goto :failed
)

py -3 -m pytest -q ^
  --basetemp="%PYTEST_BASETEMP%" ^
  tests\test_fragmenter_current_release.py ^
  tests\test_frozen_run_all_release.py ^
  tests\test_fragmenter_release_experience_v1.py ^
  tests\test_run_all_cancellation_v1.py
if errorlevel 1 goto :failed

if exist "%PYTEST_BASETEMP%" rmdir /s /q "%PYTEST_BASETEMP%"
echo.
echo Fragmenter 1.0 current-release validation passed.
pause
exit /b 0

:failed
echo.
echo Fragmenter 1.0 current-release validation failed. Review the output above.
echo Any pytest temporary files are under build\pytest-current-release.
pause
exit /b 1
