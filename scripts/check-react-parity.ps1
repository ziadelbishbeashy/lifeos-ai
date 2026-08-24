$ErrorActionPreference = "Stop"

Write-Host "[1/6] React parity bridge tests"
Push-Location backend
python -m pytest tests\test_react_ui_parity_bridge.py -v

Write-Host "[2/6] Existing React API tests"
python -m pytest tests\test_api_v1_react_phase1.py tests\test_api_v1_react_phase2.py -v

Write-Host "[3/6] Full backend regression"
python -m pytest

Write-Host "[4/6] Migration head"
python -m flask --app app db current
Pop-Location

Write-Host "[5/6] Frontend production build"
Push-Location frontend
npm install
npm run build
Pop-Location

Write-Host "[6/6] Done"
Write-Host "Start backend with: cd backend; python app.py"
Write-Host "Start frontend with: cd frontend; npm run dev"
