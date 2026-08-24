$ErrorActionPreference = "Stop"

Write-Host "Cleaning obsolete React parity/bridge files..."

$paths = @(
  "frontend\src\legacy",
  "frontend\src\native\useNativeLegacyAssets.ts",
  "frontend\src\auth\PublicOnly.tsx",
  "frontend\src\auth\RequireAuth.tsx",
  "frontend\src\components\AppShell.tsx",
  "frontend\src\pages\MigrationPage.tsx",
  "frontend\src\pages\OverviewPage.tsx",
  "frontend\src\styles\legacy",
  "frontend\public\static",
  "frontend\scripts\sync-legacy-assets.mjs",
  "backend\lifeos\api\v1\legacy_ui.py",
  "frontend\tsconfig.app.tsbuildinfo",
  "frontend\tsconfig.node.tsbuildinfo"
)

foreach ($path in $paths) {
  if (Test-Path $path) {
    Remove-Item $path -Recurse -Force
    Write-Host "Removed $path"
  }
}

if ((Test-Path "frontend\scripts") -and -not (Get-ChildItem "frontend\scripts" -Force | Select-Object -First 1)) {
  Remove-Item "frontend\scripts" -Force
}

Write-Host "Cleanup complete. Run .\scripts\check-react-parity.ps1 next."
