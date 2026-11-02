# Start the local simulator and the Streamlit dashboard together.
#
#   .\scripts\demo.ps1
#   .\scripts\demo.ps1 -Duration 300 -Port 8502
#   .\scripts\demo.ps1 -Reset          # delete the demo database first
#
# The simulator writes straight to SQLite (no broker required).
[CmdletBinding()]
param(
    [string]$Python,
    [int]$Duration = 180,
    [string]$Database = "data\gridshield.db",
    [int]$Port = 8501,
    [switch]$Reset,
    [switch]$NoSimulator
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\_common.ps1"

$root = Get-GridShieldRoot
$python = Resolve-GridShieldPython -Python $Python

if ([System.IO.Path]::IsPathRooted($Database)) {
    $dbPath = $Database
}
else {
    $dbPath = Join-Path $root $Database
}

if ($Reset -and (Test-Path -LiteralPath $dbPath)) {
    Write-Host "Removing $dbPath"
    Remove-Item -LiteralPath $dbPath -Force
    Get-ChildItem -LiteralPath (Split-Path -Parent $dbPath) -Filter ((Split-Path -Leaf $dbPath) + "-*") -ErrorAction SilentlyContinue |
        Remove-Item -Force -ErrorAction SilentlyContinue
}

New-Item -ItemType Directory -Force -Path (Split-Path -Parent $dbPath) | Out-Null
$env:GRIDSHIELD_DB = $dbPath

if (-not (Test-Path -LiteralPath (Join-Path $root "models\isolation_forest.joblib"))) {
    Write-Warning "Maintenance model missing; run .\scripts\train.ps1 for degradation scoring."
}

$simulator = $null
if (-not $NoSimulator) {
    # Start-Process does not quote array elements itself, and the project path
    # contains a space. Build one quoted argument string explicitly.
    $simArgs = "-m sim.run --mode local --duration $Duration --db `"$dbPath`""
    Write-Host "Starting simulator for $Duration s ..."
    $simulator = Start-Process -FilePath $python -ArgumentList $simArgs `
        -WorkingDirectory $root -NoNewWindow -PassThru
}

try {
    Write-Host ""
    Write-Host "Dashboard: http://localhost:$Port"
    Write-Host "Press Ctrl+C to stop."
    Write-Host ""
    Invoke-GridShieldNative -FilePath $python -Arguments @(
        "-m", "streamlit", "run", (Join-Path $root "dashboard\app.py"),
        "--server.port", "$Port", "--server.headless", "true",
        "--browser.gatherUsageStats", "false"
    ) | Out-Null
}
finally {
    if ($simulator -and -not $simulator.HasExited) {
        Write-Host "Stopping simulator ..."
        Stop-Process -Id $simulator.Id -Force -ErrorAction SilentlyContinue
    }
}
