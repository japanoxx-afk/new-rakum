param(
    [string]$ExePath = "C:\Program Files (x86)\TriggerSoft\RhakMu\Rhakmu.exe"
)

$ErrorActionPreference = "Stop"

function Convert-VaToFileOffset([byte[]]$Bytes, [uint32]$Va) {
    $pe = [BitConverter]::ToUInt32($Bytes, 0x3C)
    $imageBase = [BitConverter]::ToUInt32($Bytes, $pe + 0x34)
    $sections = [BitConverter]::ToUInt16($Bytes, $pe + 0x06)
    $optSize = [BitConverter]::ToUInt16($Bytes, $pe + 0x14)
    $secOff = $pe + 0x18 + $optSize

    for ($i = 0; $i -lt $sections; $i++) {
        $off = $secOff + ($i * 40)
        $virtualSize = [BitConverter]::ToUInt32($Bytes, $off + 8)
        $virtualAddress = [BitConverter]::ToUInt32($Bytes, $off + 12)
        $rawSize = [BitConverter]::ToUInt32($Bytes, $off + 16)
        $rawPtr = [BitConverter]::ToUInt32($Bytes, $off + 20)
        $start = $imageBase + $virtualAddress
        $size = [Math]::Max($virtualSize, $rawSize)
        $end = $start + $size
        if ($Va -ge $start -and $Va -lt $end) {
            return [int]($rawPtr + ($Va - $start))
        }
    }

    throw ("VA 0x{0:X8} is not inside a PE section" -f $Va)
}

function Test-BytesEqual([byte[]]$A, [byte[]]$B) {
    if ($A.Length -ne $B.Length) { return $false }
    for ($i = 0; $i -lt $A.Length; $i++) {
        if ($A[$i] -ne $B[$i]) { return $false }
    }
    return $true
}

if (-not (Test-Path -LiteralPath $ExePath)) {
    throw "File not found: $ExePath"
}

$bytes = [IO.File]::ReadAllBytes($ExePath)

# CGameMenu::ProcessWndProc calls iCARUS_RestoreSurfaces during focus/display
# messages. On modern DirectDraw wrappers this can fire while the surface
# pointer is null during the menu-to-game transition. Skip this opportunistic
# restore; normal surface creation still happens through iCARUS_InitDDraw.
$va = [uint32]0x00424416
$offset = Convert-VaToFileOffset $bytes $va
$expected = [byte[]]@(0xFF,0x15,0x58,0xB5,0x4E,0x00)
$patch = [byte[]]@(0x90,0x90,0x90,0x90,0x90,0x90)

$current = New-Object byte[] $expected.Length
[Array]::Copy($bytes, $offset, $current, 0, $current.Length)

if (Test-BytesEqual $current $patch) {
    Write-Host "Already patched: iCARUS_RestoreSurfaces message guard" -ForegroundColor Yellow
    return
}

if (-not (Test-BytesEqual $current $expected)) {
    $hex = ($current | ForEach-Object { "{0:X2}" -f $_ }) -join " "
    throw "Unexpected bytes at VA 0x$('{0:X8}' -f $va), file offset 0x$('{0:X}' -f $offset): $hex"
}

$backup = "$ExePath.bak_icarusrestore_$(Get-Date -Format yyyyMMdd_HHmmss)"
[IO.File]::WriteAllBytes($backup, $bytes)

[Array]::Copy($patch, 0, $bytes, $offset, $patch.Length)
[IO.File]::WriteAllBytes($ExePath, $bytes)

Write-Host "Patched iCARUS_RestoreSurfaces message guard." -ForegroundColor Green
Write-Host "Backup: $backup"
