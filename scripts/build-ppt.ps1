# Build the PowerPoint report (and a PDF preview when PowerPoint is installed).
#
#   .\scripts\build-ppt.ps1
#   .\scripts\build-ppt.ps1 -Open
#   .\scripts\build-ppt.ps1 -Capture          # fresh dashboard screenshot first
#   .\scripts\build-ppt.ps1 -Python "C:\path\to\python.exe"
#
# Output: build\GridShield-Report.pptx
#         build\GridShield-Report.pdf        (if PowerPoint COM is available)
#
# Needs python-pptx and matplotlib. A fresh dashboard capture additionally needs
# playwright plus an installed Chrome or Edge; the browser is driven headless,
# no browser download is required.
[CmdletBinding()]
param(
    [string]$Python,
    [switch]$Capture,
    [switch]$Open
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\_common.ps1"

$root = Get-GridShieldRoot
$python = Resolve-GridShieldPython -Python $Python
$img = Join-Path $root "build\img"

function Ensure-Module([string]$Name) {
    $code = Invoke-GridShieldPython -Python $python -Arguments @(
        "-c", "import $Name"
    )
    if ($code -ne 0) {
        Write-Host "Installing $Name ..."
        $code = Invoke-GridShieldPython -Python $python -Arguments @(
            "-m", "pip", "install", "--quiet", $Name
        )
        if ($code -ne 0) { throw "Could not install '$Name'." }
    }
}

Ensure-Module "pptx"
New-Item -ItemType Directory -Force -Path $img | Out-Null

# --- reference sheets as PNG (the deck embeds them) -------------------------
$sheets = @{
    1 = "circuit-sheet-1-power.svg"
    2 = "circuit-sheet-2-isolation.svg"
    3 = "circuit-sheet-3-mcu-io.svg"
}

$browser = @(
    "C:\Program Files\Google\Chrome\Application\chrome.exe",
    "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "C:\Program Files\Microsoft\Edge\Application\msedge.exe"
) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1

foreach ($n in 1, 2, 3) {
    $png = Join-Path $img "sheet$n.png"
    $svg = Join-Path $root "docs\$($sheets[$n])"
    if (-not (Test-Path -LiteralPath $svg)) { throw "Missing schematic $($sheets[$n])." }
    if ((Test-Path -LiteralPath $png) -and -not $Capture) { continue }
    if (-not $browser) {
        Write-Host "Chrome/Edge not found - keeping the existing sheet$n.png"
        continue
    }
    Write-Host "Rendering $($sheets[$n]) ..."
    $resolved = (Resolve-Path -LiteralPath $svg).ProviderPath
    $uri = ([System.Uri]$resolved).AbsoluteUri
    $code = Invoke-GridShieldNative -FilePath $browser -Arguments @(
        "--headless=new", "--disable-gpu", "--hide-scrollbars",
        "--force-device-scale-factor=2", "--window-size=1600,1060",
        "--screenshot=$png", $uri
    )
    if ($code -ne 0 -or -not (Test-Path -LiteralPath $png)) {
        throw "Could not render $($sheets[$n]) to PNG."
    }
}

# --- optional live dashboard screenshot ------------------------------------
$dash = Join-Path $img "dashboard.png"
if ($Capture -or -not (Test-Path -LiteralPath $dash)) {
    Write-Host "Capturing the dashboard (about 2 minutes) ..."
    Ensure-Module "playwright"
    $code = Invoke-GridShieldPython -Python $python -Arguments @(
        "scripts\capture_dashboard.py"
    )
    if ($code -ne 0) {
        Write-Host "WARNING: dashboard capture failed - the slide will be skipped."
    }
}

# --- charts and the deck ---------------------------------------------------
Write-Host "Building report figures ..."
$code = Invoke-GridShieldPython -Python $python -Arguments @("scripts\make_ppt_figures.py")
if ($code -ne 0) { throw "make_ppt_figures.py failed." }

Write-Host "Building PowerPoint ..."
$code = Invoke-GridShieldPython -Python $python -Arguments @("scripts\make_ppt.py")
if ($code -ne 0) { throw "make_ppt.py failed." }

$pptx = Join-Path $root "build\GridShield-Report.pptx"
if (-not (Test-Path -LiteralPath $pptx)) { throw "PPTX was not created." }

# --- PDF preview via PowerPoint COM (best effort) --------------------------
$pdf = Join-Path $root "build\GridShield-Report.pdf"
$powerpoint = @(
    "C:\Program Files\Microsoft Office\root\Office16\POWERPNT.EXE",
    "C:\Program Files (x86)\Microsoft Office\root\Office16\POWERPNT.EXE"
) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1

if ($powerpoint) {
    Write-Host "Exporting PDF preview ..."
    try {
        $app = New-Object -ComObject PowerPoint.Application
        try {
            $pres = $app.Presentations.Open($pptx, $true, $false, $false)
            $pres.SaveAs($pdf, 32)   # ppSaveAsPDF
            $pres.Close()
        }
        finally {
            $app.Quit()
            [System.Runtime.InteropServices.Marshal]::ReleaseComObject($app) | Out-Null
        }
    }
    catch {
        Write-Host "WARNING: PDF preview failed ($($_.Exception.Message))"
    }
}

Write-Host ""
Write-Host "PPTX: $pptx"
if (Test-Path -LiteralPath $pdf) { Write-Host "PDF : $pdf" }

if ($Open) {
    Start-Process -FilePath $pptx
}
