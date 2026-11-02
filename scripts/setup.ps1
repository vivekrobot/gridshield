# Create a virtual environment, install dependencies and copy local config.
#
#   .\scripts\setup.ps1
#   .\scripts\setup.ps1 -Python "C:\Python312\python.exe"   # reuse an interpreter
#   .\scripts\setup.ps1 -Force                              # recreate .venv
[CmdletBinding()]
param(
    [string]$Python,
    [switch]$Force,
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\_common.ps1"

$root = Get-GridShieldRoot
$venvDir = Join-Path $root ".venv"
$venvPython = Join-Path $venvDir "Scripts\python.exe"

if ($Python) {
    $basePython = Resolve-GridShieldPython -Python $Python
}
elseif (Test-Path -LiteralPath $venvPython) {
    $basePython = $venvPython
}
else {
    $command = Get-Command python -ErrorAction SilentlyContinue
    if (-not $command) {
        throw "Python is not on PATH. Install Python 3.10+ or pass -Python <path>."
    }
    $basePython = $command.Source
}

Write-Host "Project root : $root"
Write-Host "Base Python  : $basePython"

if ($Force -and (Test-Path -LiteralPath $venvDir)) {
    Write-Host "Removing existing .venv ..."
    Remove-Item -LiteralPath $venvDir -Recurse -Force
}

if (-not (Test-Path -LiteralPath $venvPython)) {
    Write-Host "Creating virtual environment .venv ..."
    $code = Invoke-GridShieldNative -FilePath $basePython -Arguments @("-m", "venv", $venvDir)
    if ($code -ne 0) { throw "python -m venv failed with exit code $code" }
}

if (-not $SkipInstall) {
    Write-Host "Installing requirements ..."
    $code = Invoke-GridShieldNative -FilePath $venvPython -Arguments @("-m", "pip", "install", "--upgrade", "pip")
    if ($code -ne 0) { throw "pip upgrade failed with exit code $code" }
    $code = Invoke-GridShieldNative -FilePath $venvPython `
        -Arguments @("-m", "pip", "install", "-r", (Join-Path $root "requirements.txt"))
    if ($code -ne 0) { throw "dependency installation failed with exit code $code" }
}

$envExample = Join-Path $root ".env.example"
$envFile = Join-Path $root ".env"
if ((Test-Path -LiteralPath $envExample) -and -not (Test-Path -LiteralPath $envFile)) {
    Copy-Item -LiteralPath $envExample -Destination $envFile
    Write-Host "Created .env from .env.example"
}

$secretsExample = Join-Path $root "firmware\arduino\gridshield_node\secrets.example.h"
$secretsFile = Join-Path $root "firmware\arduino\gridshield_node\secrets.h"
if ((Test-Path -LiteralPath $secretsExample) -and -not (Test-Path -LiteralPath $secretsFile)) {
    Copy-Item -LiteralPath $secretsExample -Destination $secretsFile
    Write-Host "Created firmware secrets.h from secrets.example.h (edit Wi-Fi/MQTT values)"
}

Write-Host ""
Write-Host "Setup complete."
Write-Host "  Train models : .\scripts\train.ps1"
Write-Host "  Run a demo   : .\scripts\demo.ps1 -Duration 180"
Write-Host "  Run tests    : .\scripts\test.ps1"
