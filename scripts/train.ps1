# Train the PQD 1D-CNN (and regenerate the firmware header) and the
# Isolation Forest maintenance model.
#
#   .\scripts\train.ps1
#   .\scripts\train.ps1 -PerClass 800 -Epochs 50
#   .\scripts\train.ps1 -SkipCnn
#   .\scripts\train.ps1 -Python "C:\path\to\python.exe"
[CmdletBinding()]
param(
    [string]$Python,
    [int]$PerClass = 600,
    [int]$Epochs = 40,
    [int]$Rows = 5000,
    [double]$Contamination = 0.05,
    [switch]$ReuseDataset,
    [switch]$SkipCnn,
    [switch]$SkipAnomaly
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\_common.ps1"

$root = Get-GridShieldRoot
$python = Resolve-GridShieldPython -Python $Python
Write-Host "Using Python: $python"

if (-not $SkipCnn) {
    Write-Host ""
    Write-Host "== Training 1D-CNN =="
    $cnnArgs = @("-m", "ml.train_cnn", "--per-class", "$PerClass", "--epochs", "$Epochs")
    if ($ReuseDataset) { $cnnArgs += "--reuse-dataset" }
    $code = Invoke-GridShieldPython -Python $python -Arguments $cnnArgs -WorkingDirectory $root
    if ($code -ne 0) { throw "CNN training failed with exit code $code" }
}

if (-not $SkipAnomaly) {
    Write-Host ""
    Write-Host "== Training Isolation Forest =="
    $anomalyArgs = @(
        "-m", "ml.train_anomaly",
        "--rows", "$Rows",
        "--contamination", "$Contamination"
    )
    $code = Invoke-GridShieldPython -Python $python -Arguments $anomalyArgs -WorkingDirectory $root
    if ($code -ne 0) { throw "anomaly training failed with exit code $code" }
}

Write-Host ""
Write-Host "Done. Artefacts:"
Write-Host "  models\cnn_weights.npz, models\cnn_model_card.json"
Write-Host "  models\isolation_forest.joblib, models\anomaly_meta.json"
Write-Host "  reports\cnn_metrics.json, reports\*.png"
Write-Host "  firmware\arduino\gridshield_node\model_weights.h"
Write-Host ""
Write-Host "Run .\scripts\test.ps1 to verify the exported model."
