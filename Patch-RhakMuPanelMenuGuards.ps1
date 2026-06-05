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

# CPannelMgr::ProcessMenu can run one frame after the active menu object starts
# tearing down during the menu-to-game transition. The stock code checks only
# the list slot pointer, then calls through the menu object's vtable:
#   mov edx, [menu]
#   mov ecx, menu
#   call dword ptr [edx+30h]
# If the object is half-destroyed, edx is null and the client crashes at
# CPannelMgr::ProcessMenu()+0095. Rebuild the small block with object and
# vtable guards; if either is null, keep the existing -1 menu id and fall into
# the function's normal out-of-range/default path.
$va = [uint32]0x00462822
$offset = Convert-VaToFileOffset $bytes $va
$expected = [byte[]]@(
    0x8B,0x10,
    0x89,0x55,0xE0,
    0x8B,0x45,0xE0,
    0x8B,0x10,
    0x8B,0x4D,0xE0,
    0xFF,0x52,0x30,
    0x8B,0x00,
    0x89,0x45,0xF8,
    0x0F,0xBF,0x4D,0xF8,
    0x89,0x4D,0xDC,
    0x8B,0x55,0xDC,
    0x83,0xEA,0x3C,
    0x89,0x55,0xDC
)
$patch = [byte[]]@(
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
    0x90,0x90,0x90,0x90,0x90,0x90,0x90
)

$current = New-Object byte[] $expected.Length
[Array]::Copy($bytes, $offset, $current, 0, $current.Length)

if (Test-BytesEqual $current $patch) {
    Write-Host "Already patched: CPannelMgr::ProcessMenu vtable guard" -ForegroundColor Yellow
    return
}

if (-not (Test-BytesEqual $current $expected)) {
    $hex = ($current | ForEach-Object { "{0:X2}" -f $_ }) -join " "
    throw "Unexpected bytes at VA 0x$('{0:X8}' -f $va), file offset 0x$('{0:X}' -f $offset): $hex"
}

$backup = "$ExePath.bak_panelmenu_$(Get-Date -Format yyyyMMdd_HHmmss)"
[IO.File]::WriteAllBytes($backup, $bytes)

[Array]::Copy($patch, 0, $bytes, $offset, $patch.Length)
[IO.File]::WriteAllBytes($ExePath, $bytes)

Write-Host "Patched CPannelMgr::ProcessMenu vtable guard." -ForegroundColor Green
Write-Host "Backup: $backup"
