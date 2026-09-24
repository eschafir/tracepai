docker rm -f tracepai 2>$null | Out-Null
if ($LASTEXITCODE -eq 0) { Write-Host "TracepAI stopped" } else { Write-Host "TracepAI is not running" }
