$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$target = Join-Path $root 'backend\lifeos\api\v1\documents.py'

if (-not (Test-Path $target)) {
    throw "Could not find $target"
}

$text = Get-Content -Raw -Path $target

$functionMarker = '@documents_api_bp.get("/<int:document_id>/file")'
$start = $text.IndexOf($functionMarker)
if ($start -lt 0) {
    throw 'Could not find the API document file route.'
}

$nextRoute = $text.IndexOf("`n`n@documents_api_bp.", $start + $functionMarker.Length)
if ($nextRoute -lt 0) {
    $nextRoute = $text.Length
}

$before = $text.Substring(0, $start)
$route = $text.Substring($start, $nextRoute - $start)
$after = $text.Substring($nextRoute)

if ($route -match 'X-Frame-Options.*SAMEORIGIN') {
    Write-Host 'PDF viewer header is already fixed.' -ForegroundColor Green
    exit 0
}

$needle = '    response.headers["Cache-Control"] = "private, no-store, max-age=0"'
$replacement = @'
    response.headers["Cache-Control"] = "private, no-store, max-age=0"
    response.headers["Pragma"] = "no-cache"
    # This private PDF endpoint is intentionally embedded by the same-origin
    # React workspace. Override the global DENY policy only for this route.
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
'@

if (-not $route.Contains($needle)) {
    throw 'Could not locate the PDF response headers in the API file route.'
}

$route = $route.Replace($needle, $replacement.TrimEnd("`r", "`n"))
Set-Content -Path $target -Value ($before + $route + $after) -Encoding UTF8

Write-Host 'Fixed API PDF inline viewer security header.' -ForegroundColor Green
Write-Host 'Restart Flask, then hard-refresh the Document Brain PDF tab.' -ForegroundColor Cyan
