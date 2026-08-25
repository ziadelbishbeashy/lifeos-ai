$ErrorActionPreference = "Stop"

Write-Host "[1/7] Frontend/backend separation contract"
Push-Location backend
python -m pytest tests\test_react_ui_parity_bridge.py -v

Write-Host "[2/7] React API regression"
python -m pytest tests\test_api_v1_react_phase1.py tests\test_api_v1_react_phase2.py -v

Write-Host "[3/7] Full backend regression"
python -m pytest

Write-Host "[4/7] Migration head"
python -m flask --app app db current
Pop-Location

Write-Host "[5/7] Frontend separation source scan"
$bad = @()
$bad += Get-ChildItem frontend\src -Recurse -File | Select-String -SimpleMatch "/api/v1/legacy-proxy" -ErrorAction SilentlyContinue
$bad += Get-ChildItem frontend\src -Recurse -File | Select-String -SimpleMatch "react-router-dom" -ErrorAction SilentlyContinue
$bad += Get-Content frontend\package.json | Select-String -SimpleMatch "sync:legacy-ui" -ErrorAction SilentlyContinue
if ($bad.Count -gt 0) {
    $bad | ForEach-Object { Write-Host $_ }
    throw "Frontend separation scan failed. Legacy bridge/router/static-sync references remain."
}
Write-Host "No active legacy proxy, React Router v6, or backend-static sync references found."

Write-Host "[6/8] Frontend layout contract"
$mainSource = Get-Content frontend\src\main.tsx -Raw
if ($mainSource -match 'styles/global\.css') {
    throw "Layout contract failed: obsolete Phase-2 global.css is still imported."
}
if ($mainSource -notmatch 'styles/layout-foundation\.css') {
    throw "Layout contract failed: layout-foundation.css is not imported."
}
$layoutSource = Get-Content frontend\src\styles\layout-foundation.css -Raw
if ($layoutSource -notmatch '\.app-shell\s*\{[^}]*display:\s*block') {
    throw "Layout contract failed: canonical app shell override is missing."
}
Write-Host "Canonical fixed-sidebar React layout contract is active."

Write-Host "[7/8] Frontend production build"
Push-Location frontend
npm install
npm run build
npm audit --omit=dev
Pop-Location

Write-Host "[8/8] Done"
Write-Host "React owns UI. Flask owns JSON APIs/services/data/AI."
Write-Host "Start backend with: cd backend; python app.py"
Write-Host "Start frontend with: cd frontend; npm run dev"
