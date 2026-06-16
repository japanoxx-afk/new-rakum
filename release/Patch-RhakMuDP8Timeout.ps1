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

# VA 0x46518C: mov dword ptr [edx + 0x180], 7
# Bytes: C7 82 80 01 00 00 07 00 00 00
# Fix:   C7 82 80 01 00 00 00 00 00 00  (state=0 instead of state=7)
#
# When DP8 EnumHosts times out at ~10s, this callback sets state=7 which
# triggers draw. By changing state=7 to state=0, the state machine keeps
# waiting, DP8 retries, and when P2P connects at ~18s, the success callback
# sets state=6, which triggers battle start normally.
#
# PE: base=0x400000, .text VA=0x401000, .text raw offset=0x1000
# File offset = 0x46518C - 0x401000 + 0x1000 = 0x6518C
$off = 0x6518C

$expected = [byte[]]@(0xC7, 0x82, 0x80, 0x01, 0x00, 0x00, 0x07, 0x00, 0x00, 0x00)
$patched  = [byte[]]@(0xC7, 0x82, 0x80, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00)

$actual = $bytes[$off..($off + 9)]
$match = $true
for ($i = 0; $i -lt 10; $i++) {
    if ($actual[$i] -ne $expected[$i]) { $match = $false; break }
}

if ($match) {
    for ($i = 0; $i -lt 10; $i++) { $bytes[$off + $i] = $patched[$i] }
    [System.IO.File]::WriteAllBytes($ExePath, $bytes)
    Write-Host "Patched: DP8 timeout no longer triggers draw (state 7->0 at 0x46518C)" -ForegroundColor Green
} else {
    $alreadyPatched = $true
    for ($i = 0; $i -lt 10; $i++) {
        if ($actual[$i] -ne $patched[$i]) { $alreadyPatched = $false; break }
    }
    if ($alreadyPatched) {
        Write-Host "Already patched at 0x46518C" -ForegroundColor Yellow
    } else {
        Write-Host "MISMATCH at 0x6458C:" -ForegroundColor Red
        Write-Host "  Expected: $($expected | ForEach-Object { $_.ToString('X2') } | Join-String -Separator ' ')"
        Write-Host "  Actual:   $($actual   | ForEach-Object { $_.ToString('X2') } | Join-String -Separator ' ')"
        exit 1
    }
}
