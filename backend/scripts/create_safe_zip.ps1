param(
    [string]$Output = "lifeos-ai-safe.zip"
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path ".").Path
$tempRoot = Join-Path $env:TEMP ("lifeos-safe-" + [guid]::NewGuid().ToString("N"))
$copyRoot = Join-Path $tempRoot "lifeos-ai"

New-Item -ItemType Directory -Path $copyRoot -Force | Out-Null

$excludedDirectories = @(
    ".git", ".venv", "venv", "env", "__pycache__", ".pytest_cache",
    "instance", "static\uploads"
)
$excludedFiles = @(".env")

Get-ChildItem -Force $projectRoot | ForEach-Object {
    if ($excludedFiles -contains $_.Name) { return }
    if ($excludedDirectories -contains $_.Name) { return }
    Copy-Item $_.FullName $copyRoot -Recurse -Force
}

Get-ChildItem $copyRoot -Recurse -Directory -Force |
    Where-Object { $_.Name -in @("__pycache__", ".pytest_cache") } |
    Remove-Item -Recurse -Force

$destination = Join-Path $projectRoot $Output
if (Test-Path $destination) { Remove-Item $destination -Force }
Compress-Archive -Path $copyRoot -DestinationPath $destination -Force
Remove-Item $tempRoot -Recurse -Force

Write-Host "Created safe ZIP: $destination"
