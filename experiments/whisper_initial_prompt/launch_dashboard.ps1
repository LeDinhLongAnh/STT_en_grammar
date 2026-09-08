$ErrorActionPreference = "Stop"
$ExperimentDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonExe = Join-Path $ExperimentDir ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $PythonExe)) {
  throw "Whisper environment is missing. Run: .\setup.ps1 -DownloadModel"
}

& $PythonExe (Join-Path $ExperimentDir "dashboard.py")
