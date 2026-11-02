# Build the full project PDF and the reference schematics.
#
#   .\scripts\build-pdf.ps1
#   .\scripts\build-pdf.ps1 -Open
#   .\scripts\build-pdf.ps1 -Python "C:\path\to\python.exe"
#
# Output: build\GridShield-Project.pdf  (README + docs + 3 schematic sheets)
# Also regenerates docs\circuit-sheet-{1,2,3}-*.svg.
#
# Requires: the `markdown` package (pip install markdown) and Chrome or Edge.
[CmdletBinding()]
param(
    [string]$Python,
    [switch]$Open
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\_common.ps1"

$root = Get-GridShieldRoot
$python = Resolve-GridShieldPython -Python $Python

$code = Invoke-GridShieldPython -Python $python -Arguments @(
    "-c", "import markdown, sys; sys.exit(0)"
)
if ($code -ne 0) {
    Write-Host "Installing the markdown package ..."
    $code = Invoke-GridShieldPython -Python $python -Arguments @(
        "-m", "pip", "install", "--quiet", "markdown"
    )
    if ($code -ne 0) { throw "Could not install 'markdown'." }
}

Write-Host "Drawing schematics ..."
$code = Invoke-GridShieldPython -Python $python -Arguments @("scripts\make_schematics.py")
if ($code -ne 0) { throw "make_schematics.py failed." }

Write-Host "Building PDF ..."
$code = Invoke-GridShieldPython -Python $python -Arguments @("scripts\build_pdf.py")
if ($code -ne 0) { throw "build_pdf.py failed." }

$pdf = Join-Path $root "build\GridShield-Project.pdf"
if (-not (Test-Path -LiteralPath $pdf)) { throw "PDF was not created." }

Write-Host ""
Write-Host "PDF: $pdf"
if ($Open) {
    Start-Process -FilePath $pdf
}
