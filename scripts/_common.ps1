# Shared helpers for the GridShield PowerShell entry points.
# Dot-source from the other scripts:  . "$PSScriptRoot\_common.ps1"

Set-StrictMode -Version Latest

function Get-GridShieldRoot {
    return (Split-Path -Parent $PSScriptRoot)
}

function Resolve-GridShieldPython {
    param([string]$Python)

    if ($Python) {
        if (Test-Path -LiteralPath $Python) {
            return (Resolve-Path -LiteralPath $Python).Path
        }
        return $Python
    }

    $root = Get-GridShieldRoot
    $venv = Join-Path $root ".venv\Scripts\python.exe"
    if (Test-Path -LiteralPath $venv) {
        return $venv
    }

    $command = Get-Command python -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    throw "Python not found. Run scripts\setup.ps1 first, or pass -Python <path-to-python.exe>."
}

function Invoke-GridShieldNative {
    # Run a native executable without letting its stderr output trip
    # $ErrorActionPreference = "Stop" (unittest and pip both write to stderr).
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [string[]]$Arguments = @(),
        [string]$WorkingDirectory = (Get-GridShieldRoot)
    )

    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    Push-Location -LiteralPath $WorkingDirectory
    try {
        & $FilePath @Arguments | Out-Host
        return $LASTEXITCODE
    }
    finally {
        Pop-Location
        $ErrorActionPreference = $previous
    }
}

function Invoke-GridShieldPython {
    param(
        [Parameter(Mandatory = $true)][string]$Python,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [string]$WorkingDirectory = (Get-GridShieldRoot)
    )

    return Invoke-GridShieldNative -FilePath $Python -Arguments $Arguments `
        -WorkingDirectory $WorkingDirectory
}
