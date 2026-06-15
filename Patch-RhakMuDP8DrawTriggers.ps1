param(
    [string]$ExePath = "",
    [string]$GameDir = "C:\Program Files (x86)\TriggerSoft\RhakMu"
)

if ($ExePath -eq "") { $ExePath = Join-Path $GameDir "Rhakmu.exe" }
if (-not (Test-Path $ExePath)) { Write-Error "Rhakmu.exe not found: $ExePath"; exit 1 }

$bytes = [System.IO.File]::ReadAllBytes($ExePath)

# PE: base=0x400000, .text VA=0x401000, raw=0x1000
# file_offset = VA - 0x401000 + 0x1000

# Patch 1: 0x462A52  mov word ptr [0x1069d4e], 1  (DP8 failure msg A → draw)
# Instruction: 66 C7 05 4E 9D 06 01 01 00  (9 bytes)
# Fix: NOP x9
$p1_off = 0x462A52 - 0x401000 + 0x1000
$p1_exp = [byte[]]@(0x66, 0xC7, 0x05, 0x4E, 0x9D, 0x06, 0x01, 0x01, 0x00)
$p1_fix = [byte[]]@(0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90)

# Patch 2: 0x462A74  mov word ptr [0x1069d4e], 1  (DP8 failure msg B → draw)
# Same instruction bytes
$p2_off = 0x462A74 - 0x401000 + 0x1000
$p2_exp = [byte[]]@(0x66, 0xC7, 0x05, 0x4E, 0x9D, 0x06, 0x01, 0x01, 0x00)
$p2_fix = [byte[]]@(0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90)

# Patch 3: 0x462AF3  mov word ptr [0x1069d4e], 1  (state==7 → draw, already avoided by state7 patch)
# Patch this too for safety
$p3_off = 0x462AF3 - 0x401000 + 0x1000
$p3_exp = [byte[]]@(0x66, 0xC7, 0x05, 0x4E, 0x9D, 0x06, 0x01, 0x01, 0x00)
$p3_fix = [byte[]]@(0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90)

function Apply-Patch {
    param($off, $exp, $fix, $name)
    $actual = $bytes[$off..($off + $exp.Length - 1)]
    $isExp = $true; $isFix = $true
    for ($i = 0; $i -lt $exp.Length; $i++) {
        if ($actual[$i] -ne $exp[$i]) { $isExp = $false }
        if ($actual[$i] -ne $fix[$i]) { $isFix = $false }
    }
    if ($isExp) {
        for ($i = 0; $i -lt $fix.Length; $i++) { $script:bytes[$off + $i] = $fix[$i] }
        Write-Host "Patched: $name (0x$($off.ToString('X')))" -ForegroundColor Green
        return $true
    } elseif ($isFix) {
        Write-Host "Already patched: $name" -ForegroundColor Yellow
        return $false
    } else {
        Write-Host "MISMATCH at $name (0x$($off.ToString('X'))):" -ForegroundColor Red
        Write-Host "  Expected: $($exp | ForEach-Object { $_.ToString('X2') } | Join-String -Separator ' ')"
        Write-Host "  Actual:   $($actual | ForEach-Object { $_.ToString('X2') } | Join-String -Separator ' ')"
        return $false
    }
}

$changed = $false
$changed = (Apply-Patch $p1_off $p1_exp $p1_fix "DP8 fail-A draw trigger (0x462A52)") -or $changed
$changed = (Apply-Patch $p2_off $p2_exp $p2_fix "DP8 fail-B draw trigger (0x462A74)") -or $changed
$changed = (Apply-Patch $p3_off $p3_exp $p3_fix "state==7 draw trigger   (0x462AF3)") -or $changed

if ($changed) {
    [System.IO.File]::WriteAllBytes($ExePath, $bytes)
    Write-Host "`nAll DP8 draw triggers patched." -ForegroundColor Green
}
