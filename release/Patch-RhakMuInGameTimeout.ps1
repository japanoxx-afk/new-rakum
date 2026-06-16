# Patch Rhakmu.exe in-game P2P timeout from 10s to 60s
# VA 0x4460F7: cmp edx, 0x2710 (10000ms) -> cmp edx, 0xEA60 (60000ms)
# File offset: 0x460F7, immediate at offset 0x460F9

param(
    [string]$ExePath = "",
    [string]$GameDir = "C:\Program Files (x86)\TriggerSoft\RhakMu"
)

if ($ExePath -eq "") { $ExePath = Join-Path $GameDir "Rhakmu.exe" }
$exe = $ExePath
if (-not (Test-Path $exe)) { Write-Error "Not found: $exe"; exit 1 }

$bytes = [System.IO.File]::ReadAllBytes($exe)

# Verify the expected bytes before patching
# cmp edx, 0x2710 = 81 FA 10 27 00 00 at file offset 0x460F7
$patchOffset = 0x460F7
$expected = [byte[]]@(0x81, 0xFA, 0x10, 0x27, 0x00, 0x00)
$actual = $bytes[$patchOffset..($patchOffset+5)]

$match = $true
for ($i = 0; $i -lt 6; $i++) {
    if ($actual[$i] -ne $expected[$i]) { $match = $false; break }
}

if (-not $match) {
    Write-Host "Bytes at 0x460F7: $($actual | ForEach-Object { '{0:X2}' -f $_ })"
    Write-Host "Expected:          81 FA 10 27 00 00"
    # Check if already patched to 60s
    $patched = [byte[]]@(0x81, 0xFA, 0x60, 0xEA, 0x00, 0x00)
    $alreadyPatched = $true
    for ($i = 0; $i -lt 6; $i++) {
        if ($actual[$i] -ne $patched[$i]) { $alreadyPatched = $false; break }
    }
    if ($alreadyPatched) {
        Write-Host "Already patched to 60s timeout. OK."
        exit 0
    }
    Write-Error "Unexpected bytes at patch location. Aborting."
    exit 1
}

Write-Host "Patching in-game P2P timeout: 10000ms -> 60000ms"
# Change immediate from 0x2710 (bytes: 10 27 00 00) to 0xEA60 (bytes: 60 EA 00 00)
$bytes[0x460F9] = 0x60
$bytes[0x460FA] = 0xEA
$bytes[0x460FB] = 0x00
$bytes[0x460FC] = 0x00

[System.IO.File]::WriteAllBytes($exe, $bytes)
Write-Host "Done. In-game P2P timeout is now 60 seconds."
