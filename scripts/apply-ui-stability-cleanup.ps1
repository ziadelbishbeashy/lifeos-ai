$ErrorActionPreference = "Stop"

Write-Host "Cleaning obsolete frontend layout artifacts..."
$obsolete = @(
    "frontend\src\styles\global.css",
    "frontend\tsconfig.app.tsbuildinfo",
    "frontend\tsconfig.node.tsbuildinfo"
)
foreach ($path in $obsolete) {
    if (Test-Path $path) {
        Remove-Item $path -Force
        Write-Host "Removed $path"
    }
}
Write-Host "UI stability cleanup complete."
Write-Host "Next: .\scripts\check-react-parity.ps1"
