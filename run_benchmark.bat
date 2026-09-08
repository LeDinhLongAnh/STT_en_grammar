@echo off
echo ===================================================
echo     STARTING SHERPA-ONNX STT BENCHMARK TOOL
echo ===================================================
echo.
echo Loading virtual environment and launching GUI...
"experiments\whisper_initial_prompt\.venv\Scripts\python.exe" "experiments\sherpa_vi\app.py"

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] The application crashed or failed to start.
    pause
)
