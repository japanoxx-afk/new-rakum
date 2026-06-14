param([string]$GameDir = "C:\Program Files (x86)\TriggerSoft\RhakMu")
Remove-Item (Join-Path $GameDir "ddraw.dll") -Force -ErrorAction SilentlyContinue
Remove-Item (Join-Path $GameDir "ddraw.ini") -Force -ErrorAction SilentlyContinue
Write-Host "cnc-ddraw removed from $GameDir" -ForegroundColor Green
