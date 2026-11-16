$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) { py -3 -m venv (Join-Path $Root ".venv") }
$Python = Join-Path $Root ".venv\Scripts\python.exe"
& $Python -m pip install --upgrade pip
$Requirements = @(
  (Join-Path $Root "powerBI_report_validation-main\requirements.txt"),
  (Join-Path $Root "Power-BI-Playbook-Generator--main\requirements.txt"),
  (Join-Path $Root "Tableau_to_DAX_Convertor-main\requirements.txt")
)
foreach ($Requirement in $Requirements) { & $Python -m pip install -r $Requirement; if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed: $Requirement" } }
Write-Host "Setup complete. Run .\start.ps1 to launch the app." -ForegroundColor Green
