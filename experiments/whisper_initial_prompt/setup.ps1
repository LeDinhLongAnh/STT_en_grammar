param(
  [switch]$DownloadModel
)

$ErrorActionPreference = "Stop"
$ExperimentDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvDir = Join-Path $ExperimentDir ".venv"
$PythonExe = Join-Path $VenvDir "Scripts\python.exe"

if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
  throw "Python launcher 'py' was not found. Install 64-bit Python 3.12 first."
}

if (-not (Test-Path -LiteralPath $PythonExe)) {
  Write-Host "Creating Python 3.12 environment at $VenvDir"
  & py -3.12 -m venv $VenvDir
}

& $PythonExe -m pip install --upgrade pip
& $PythonExe -m pip install -r (Join-Path $ExperimentDir "requirements.txt")

if ($DownloadModel) {
  Write-Host "Downloading and loading the original Whisper base.en checkpoint..."
  & $PythonExe (Join-Path $ExperimentDir "run.py") --check-model
}

Write-Host ""
Write-Host "Ready. Run:"
Write-Host "  & '$PythonExe' '$ExperimentDir\run.py' --manifest '$ExperimentDir\manifest.tsv'"
