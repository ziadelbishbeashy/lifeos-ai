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

Push-Location frontend
try {
    Write-Host "[1/5] Install/update frontend dependencies"
    Invoke-CheckedNative "Frontend dependency install" { npm install }

    Write-Host "[2/5] CSS contract"
    Invoke-CheckedNative "CSS contract" { npm run css:check }

    Write-Host "[3/5] Production build"
    Invoke-CheckedNative "Frontend production build" { npm run build }

    Write-Host "[4/5] Browser runtime"
    Invoke-CheckedNative "Playwright Chromium install" { npx playwright install chromium }

    Write-Host "[5/5] Layout + smoke tests"
    Invoke-CheckedNative "Browser layout regression" { npm run test:layout }
    Invoke-CheckedNative "Browser critical-flow regression" { npm run test:smoke }
}
finally {
    Pop-Location
}
