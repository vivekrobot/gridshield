# Run the test suite; optionally recompile the firmware.
#
#   .\scripts\test.ps1
#   .\scripts\test.ps1 -Firmware
#   .\scripts\test.ps1 -Python "C:\path\to\python.exe"
[CmdletBinding()]
param(
    [string]$Python,
    [switch]$Firmware,
    [string]$ArduinoCli
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\_common.ps1"

$root = Get-GridShieldRoot
$python = Resolve-GridShieldPython -Python $Python
Write-Host "Using Python: $python"

$code = Invoke-GridShieldPython -Python $python `
    -Arguments @("-m", "unittest", "discover", "-s", "tests", "-v") `
    -WorkingDirectory $root
if ($code -ne 0) {
    throw "Tests failed with exit code $code"
}

if ($Firmware) {
    Write-Host ""
    Write-Host "== Compiling firmware =="

    if (-not $ArduinoCli) {
        $command = Get-Command arduino-cli -ErrorAction SilentlyContinue
        if ($command) {
            $ArduinoCli = $command.Source
        }
        else {
            $bundled = "C:\Program Files\Arduino IDE\resources\app\lib\backend\resources\arduino-cli.exe"
            if (Test-Path -LiteralPath $bundled) {
                $ArduinoCli = $bundled
            }
        }
    }

    if (-not $ArduinoCli) {
        throw "arduino-cli not found. Install it, or pass -ArduinoCli <path>."
    }

    $code = Invoke-GridShieldNative -FilePath $ArduinoCli `
        -Arguments @("compile", "--fqbn", "esp32:esp32:esp32", (Join-Path $root "firmware\arduino\gridshield_node"))
    if ($code -ne 0) {
        throw "Firmware compilation failed with exit code $code"
    }
    Write-Host "Firmware compiled successfully."
}

Write-Host ""
Write-Host "All selected checks passed."
