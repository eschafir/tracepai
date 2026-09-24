$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
$port = if ($env:PORT) { $env:PORT } else { "8000" }
docker build -t tracepai .
docker rm -f tracepai 2>$null | Out-Null
docker run -d --name tracepai -p "${port}:8000" -v tracepai-data:/data tracepai | Out-Null
Write-Host "TracepAI is running at http://localhost:$port (login: user / password)"
