<#
    Builds 0\BackupSuite.exe from source on a Windows machine.

    Usage (from the repo root, PowerShell):
        .\windows-app\build\build.ps1
#>

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$appRoot  = Join-Path $repoRoot "windows-app"
$outRoot  = Join-Path $repoRoot "0"

Write-Host "==> Creating virtual environment" -ForegroundColor Cyan
$venv = Join-Path $appRoot ".venv"
if (-not (Test-Path $venv)) { python -m venv $venv }
$python = Join-Path $venv "Scripts\python.exe"

Write-Host "==> Installing dependencies" -ForegroundColor Cyan
& $python -m pip install --upgrade pip --quiet
& $python -m pip install -r (Join-Path $appRoot "requirements.txt") --quiet
& $python -m pip install pyinstaller==6.10.0 --quiet

Write-Host "==> Building the executable" -ForegroundColor Cyan
& $python -m PyInstaller --noconfirm --clean `
    --distpath (Join-Path $appRoot "dist") `
    --workpath (Join-Path $appRoot "work") `
    (Join-Path $appRoot "build\BackupSuite.spec")

Write-Host "==> Assembling folder 0" -ForegroundColor Cyan
New-Item -ItemType Directory -Force -Path $outRoot | Out-Null
foreach ($sub in @("Data", "Apps", "Projects", "Shortcuts")) {
    New-Item -ItemType Directory -Force -Path (Join-Path $outRoot $sub) | Out-Null
}
Copy-Item (Join-Path $appRoot "dist\BackupSuite.exe") $outRoot -Force

Write-Host ""
Write-Host "Done. Portable app is at: $outRoot\BackupSuite.exe" -ForegroundColor Green
