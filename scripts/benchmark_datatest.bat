@echo off
rem Run Batch Benchmark on datatest/dataset.json
setlocal

set "ROOT=%~dp0.."
pushd "%ROOT%"

set "VENV_PYTHON=experiments\whisper_initial_prompt\.venv\Scripts\python.exe"
if exist "%VENV_PYTHON%" (
  set "PYTHON=%VENV_PYTHON%"
) else (
  set "PYTHON=python"
)

echo.
echo =======================================================
echo   Chay Batch Benchmark tren tap datatest/dataset.json
echo   Python : %PYTHON%
echo =======================================================
echo.

%PYTHON% scripts\benchmark_datatest.py %*

echo.
echo Hoan tat benchmark!
pause
popd
