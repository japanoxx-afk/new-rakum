param(
    [string]$ExePath = "",
    [string]$GameDir = "C:\Program Files (x86)\TriggerSoft\RhakMu"
)

if ($ExePath -eq "") { $ExePath = Join-Path $GameDir "Rhakmu.exe" }
if (-not (Test-Path $ExePath)) { Write-Error "Rhakmu.exe not found: $ExePath"; exit 1 }

$bytes = [System.IO.File]::ReadAllBytes($ExePath)

$nop9 = [byte[]]@(0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90)
$orig = [byte[]]@(0x66, 0xC7, 0x05, 0x4E, 0x9D, 0x06, 0x01, 0x01, 0x00)

function Revert-Patch {
    param($off, $name)
    $actual = $bytes[$off..($off + 8)]
    $isNop = $true; $isOrig = $true
    for ($i = 0; $i -lt 9; $i++) {
        if ($actual[$i] -ne $nop9[$i]) { $isNop = $false }
        if ($actual[$i] -ne $orig[$i]) { $isOrig = $false }
    }
    if ($isNop) {
        for ($i = 0; $i -lt 9; $i++) { $script:bytes[$off + $i] = $orig[$i] }
        Write-Host "Reverted: $name" -ForegroundColor Yellow
        return $true
    } elseif ($isOrig) {
        Write-Host "Already original: $name" -ForegroundColor Gray
        return $false
    } else {
        Write-Host "MISMATCH: $name" -ForegroundColor Red
        return $false
    }
}

$changed = $false
$changed = (Revert-Patch (0x462A52 - 0x401000 + 0x1000) "0x462A52 draw trigger A") -or $changed
$changed = (Revert-Patch (0x462A74 - 0x401000 + 0x1000) "0x462A74 draw trigger B") -or $changed
$changed = (Revert-Patch (0x462AF3 - 0x401000 + 0x1000) "0x462AF3 draw trigger C") -or $changed

if ($changed) {
    [System.IO.File]::WriteAllBytes($ExePath, $bytes)
    Write-Host "`nDraw trigger NOP patches reverted." -ForegroundColor Green
}
