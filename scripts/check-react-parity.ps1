$ErrorActionPreference = "Stop"

function Invoke-CheckedNative {
    param(
        [Parameter(Mandatory = $true)][string]$Label,
        [Parameter(Mandatory = $true)][scriptblock]$Command
    )

    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Label failed with exit code $LASTEXITCODE."
    }
}

Write-Host "[1/10] Frontend/backend separation contract"
Push-Location backend
try {
    Invoke-CheckedNative "Frontend/backend separation contract" { python -m pytest tests\test_react_ui_parity_bridge.py -v }

    Write-Host "[2/10] React API regression"
    Invoke-CheckedNative "React API regression" { python -m pytest tests\test_api_v1_react_phase1.py tests\test_api_v1_react_phase2.py -v }

    Write-Host "[3/10] Full backend regression"
    Invoke-CheckedNative "Full backend regression" { python -m pytest }

    Write-Host "[4/10] Migration head"
    Invoke-CheckedNative "Migration head check" { python -m flask --app app db current }
}
finally {
    Pop-Location
}

Write-Host "[5/10] Frontend separation source scan"
$bad = @()
$bad += Get-ChildItem frontend\src -Recurse -File | Select-String -SimpleMatch "/api/v1/legacy-proxy" -ErrorAction SilentlyContinue
$bad += Get-ChildItem frontend\src -Recurse -File | Select-String -SimpleMatch "react-router-dom" -ErrorAction SilentlyContinue
$bad += Get-Content frontend\package.json | Select-String -SimpleMatch "sync:legacy-ui" -ErrorAction SilentlyContinue
if ($bad.Count -gt 0) {
    $bad | ForEach-Object { Write-Host $_ }
    throw "Frontend separation scan failed. Legacy bridge/router/static-sync references remain."
}
Write-Host "No active legacy proxy, React Router v6, or backend-static sync references found."

Write-Host "[6/10] Frontend CSS/layout contract"
Invoke-CheckedNative "Frontend CSS/layout contract" { node frontend\scripts\check-css-contract.mjs }

Write-Host "[7/10] Frontend production build and production dependency audit"
Push-Location frontend
try {
    Invoke-CheckedNative "Frontend dependency install" { npm install }
    Invoke-CheckedNative "Frontend production build" { npm run build }
    Invoke-CheckedNative "Production dependency audit" { npm audit --omit=dev }

    Write-Host "[8/10] Playwright Chromium availability"
    Invoke-CheckedNative "Playwright Chromium install" { npx playwright install chromium }

    Write-Host "[9/10] Browser layout + critical-flow regression"
    Invoke-CheckedNative "Browser layout regression" { npm run test:layout }
    Invoke-CheckedNative "Browser critical-flow regression" { npm run test:smoke }
}
finally {
    Pop-Location
}

Write-Host "[10/10] Done"
Write-Host "React owns UI. Flask owns JSON APIs/services/data/AI."
Write-Host "Browser regression coverage is active for layout, Focus Studio, Document Brain, Projects, Tasks and Notes."
Write-Host "Visual screenshot baselines remain opt-in until you visually approve the UI."
Write-Host "Start backend with: cd backend; python app.py"
Write-Host "Start frontend with: cd frontend; npm run dev"
