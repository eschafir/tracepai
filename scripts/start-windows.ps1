$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
$port = if ($env:PORT) { $env:PORT } else { "8000" }
# The host's time zone as an IANA name (e.g. America/New_York), so "today" in the app is the same day as on this computer
$tz = "UTC"
$iana = $null
try {  # needs PowerShell 7; Windows PowerShell 5.1 keeps UTC
    if ([System.TimeZoneInfo]::TryConvertWindowsIdToIanaId([System.TimeZoneInfo]::Local.Id, [ref]$iana)) { $tz = $iana }
} catch {}
docker build -t tracepai .
docker rm -f tracepai 2>$null | Out-Null
docker run -d --name tracepai -p "${port}:8000" -e TRACEPAI_SEED_DEMO=1 -e "TZ=$tz" -v tracepai-data:/data tracepai | Out-Null
Write-Host "TracepAI is running at http://localhost:$port (login: user / password)"
