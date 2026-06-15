param(
    [string]$ExePath = "",
    [string]$GameDir = "C:\Program Files (x86)\TriggerSoft\RhakMu"
)

if ($ExePath -eq "") { $ExePath = Join-Path $GameDir "Rhakmu.exe" }

if (-not (Test-Path $ExePath)) {
    Write-Error "Rhakmu.exe not found at: $ExePath"
    exit 1
}

$bytes = [System.IO.File]::ReadAllBytes($ExePath)

# Revert Patch-RhakMuDP8Timeout.ps1: change state=0 back to state=7
# at file offset 0x6518C
$off = 0x6518C

$patched  = [byte[]]@(0xC7, 0x82, 0x80, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00)  # state=0 (patched)
$original = [byte[]]@(0xC7, 0x82, 0x80, 0x01, 0x00, 0x00, 0x07, 0x00, 0x00, 0x00)  # state=7 (original)

$actual = $bytes[$off..($off + 9)]
$isPatched = $true
for ($i = 0; $i -lt 10; $i++) {
    if ($actual[$i] -ne $patched[$i]) { $isPatched = $false; break }
}

if ($isPatched) {
    for ($i = 0; $i -lt 10; $i++) { $bytes[$off + $i] = $original[$i] }
    [System.IO.File]::WriteAllBytes($ExePath, $bytes)
    Write-Host "Reverted: 0x46518C state=0 -> state=7 (original)" -ForegroundColor Yellow
} else {
    $isOriginal = $true
    for ($i = 0; $i -lt 10; $i++) {
        if ($actual[$i] -ne $original[$i]) { $isOriginal = $false; break }
    }
    if ($isOriginal) {
        Write-Host "Already original (not patched)" -ForegroundColor Yellow
    } else {
        Write-Host "Unknown bytes at 0x6518C:" -ForegroundColor Red
        Write-Host "  $($actual | ForEach-Object { $_.ToString('X2') } | Join-String -Separator ' ')"
    }
}
