$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) { throw "Dependencies are not installed. Run .\setup.ps1 first." }
& $Python (Join-Path $Root "run.py")
