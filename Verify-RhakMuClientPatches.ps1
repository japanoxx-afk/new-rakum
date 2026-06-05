param(
    [string]$ExePath = "C:\Program Files (x86)\TriggerSoft\RhakMu\Rhakmu.exe"
)

$ErrorActionPreference = "Stop"

function Convert-VaToFileOffset([byte[]]$Bytes, [uint32]$TargetVa) {
    $pe = [BitConverter]::ToUInt32($Bytes, 0x3C)
    $imageBase = [BitConverter]::ToUInt32($Bytes, $pe + 0x34)
    $sections = [BitConverter]::ToUInt16($Bytes, $pe + 0x06)
    $optSize = [BitConverter]::ToUInt16($Bytes, $pe + 0x14)
    $secOff = $pe + 0x18 + $optSize

    for ($i = 0; $i -lt $sections; $i++) {
        $off = $secOff + ($i * 40)
        $virtualSize = [BitConverter]::ToUInt32($Bytes, $off + 8)
        $sectionVa = [BitConverter]::ToUInt32($Bytes, $off + 12)
        $rawSize = [BitConverter]::ToUInt32($Bytes, $off + 16)
        $rawPtr = [BitConverter]::ToUInt32($Bytes, $off + 20)
        $start = $imageBase + $sectionVa
        $size = [Math]::Max($virtualSize, $rawSize)
        $end = $start + $size
        if ($TargetVa -ge $start -and $TargetVa -lt $end) {
            return [int]($rawPtr + ($TargetVa - $start))
        }
    }

    throw ("VA 0x{0:X8} is not inside a PE section" -f $TargetVa)
}

function Test-BytesEqual([byte[]]$Bytes, [int]$Offset, [byte[]]$Expected) {
    if ($Offset -lt 0 -or ($Offset + $Expected.Length) -gt $Bytes.Length) { return $false }
    for ($i = 0; $i -lt $Expected.Length; $i++) {
        if ($Bytes[$Offset + $i] -ne $Expected[$i]) { return $false }
    }
    return $true
}

function Test-Nops([byte[]]$Bytes, [uint32]$Va, [int]$Length, [string]$Name) {
    $off = Convert-VaToFileOffset $Bytes $Va
    $ok = $true
    for ($i = 0; $i -lt $Length; $i++) {
        if ($Bytes[$off + $i] -ne 0x90) {
            $ok = $false
            break
        }
    }
    [pscustomobject]@{
        Name = $Name
        Status = if ($ok) { "OK" } else { "MISSING" }
        VA = ("0x{0:X8}" -f $Va)
    }
}

function Test-ExactPatch([byte[]]$Bytes, [uint32]$Va, [byte[]]$Expected, [string]$Name) {
    $off = Convert-VaToFileOffset $Bytes $Va
    $ok = Test-BytesEqual $Bytes $off $Expected
    [pscustomobject]@{
        Name = $Name
        Status = if ($ok) { "OK" } else { "MISSING" }
        VA = ("0x{0:X8}" -f $Va)
    }
}

if (-not (Test-Path -LiteralPath $ExePath)) {
    throw "File not found: $ExePath"
}

$bytes = [IO.File]::ReadAllBytes($ExePath)
$checks = New-Object System.Collections.Generic.List[object]

$battleStartPatch = [byte[]]@(
    0xC6,0x05,0x74,0xFC,0x6D,0x00,0x05,
    0x33,0xC0,0xA3,0x70,0x09,0x6E,0x00,
    0x5F,0x5E,0x5B,0x8B,0xE5,0x5D,0xC3,
    0x90,0x90
)

[void]$checks.Add((Test-ExactPatch $bytes 0x0044D2E2 $battleStartPatch "Battle start countdown sync"))
[void]$checks.Add((Test-Nops $bytes 0x0041E2AE 12 "CScenChannel scalar delete guard"))
[void]$checks.Add((Test-Nops $bytes 0x0041EF0E 12 "CScenGuild scalar delete guard"))
[void]$checks.Add((Test-Nops $bytes 0x00421B7E 12 "CScenRanking scalar delete guard"))
[void]$checks.Add((Test-Nops $bytes 0x0041E2E5 8 "CScenChannel form cleanup guard"))
[void]$checks.Add((Test-Nops $bytes 0x0041EF45 8 "CScenGuild form cleanup guard"))
[void]$checks.Add((Test-Nops $bytes 0x00421BB5 8 "CScenRanking form cleanup guard"))

$panelMenuGuardPatch = [byte[]]@(
    0x8B,0x10,
    0x85,0xD2,
    0x74,0x0E,
    0x8B,0x02,
    0x85,0xC0,
    0x74,0x08,
    0x8B,0xCA,
    0xFF,0x50,0x30,
    0x8B,0x00,
    0x89,0x45,0xF8,
    0x0F,0xBF,0x4D,0xF8,
    0x83,0xE9,0x3C,
    0x89,0x4D,0xDC,
    0x83,0x7D,0xDC,0x4F,
    0x90,0x90,0x90,0x90,0x90
)
[void]$checks.Add((Test-ExactPatch $bytes 0x00462822 $panelMenuGuardPatch "CPannelMgr menu vtable guard"))
[void]$checks.Add((Test-Nops $bytes 0x00424416 6 "iCARUS RestoreSurfaces message guard"))

$checks | Format-Table -AutoSize

if (($checks | Where-Object { $_.Status -ne "OK" }).Count -gt 0) {
    Write-Host ""
    Write-Host "One or more client patches are missing. Run the patch scripts on this PC, then verify again." -ForegroundColor Yellow
    exit 1
}

Write-Host ""
Write-Host "All checked RhakMu client patches are present." -ForegroundColor Green
