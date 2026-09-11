$ErrorActionPreference = "Stop"

python -m compileall -q .
python -m pytest
python -m flask --app app db current

Write-Host "LifeOS architecture checks completed successfully."
