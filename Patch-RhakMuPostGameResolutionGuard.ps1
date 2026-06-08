param(
    [string]$ExePath = "C:\Program Files (x86)\TriggerSoft\RhakMu\Rhakmu.exe"
)

# After a match ends, CGameMenu::Menu_GameAfterProcess (CGameMenu.cpp line 190)
# calls classSCREEN::ResolutionChange(.., 1024, 768) to restore the menu
# resolution. That re-runs iCARUS_Init -> iCARUS_InitDDraw, which crashes with
# an ACCESS_VIOLATION inside apphelp.dll (DirectDraw re-init under the Win compat
# shim) -- the host crashes right after the game ends / draws.
#
# Under DDrawCompat (borderless + desktop), the real display mode never changes,
# so this post-game ResolutionChange is redundant. NOP the entire call setup
# (push 0x300 / push 0x400 / push this->[0x30c] / mov ecx,0x10694d0 / call) at
# VA 0x004230A6..0x004230C3 (30 bytes). ResolutionChange is __thiscall with
# callee stack cleanup, so removing the pushes too keeps the stack balanced.

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
        if ($Va -ge $start -and $Va -lt ($start + $size)) {
            return [int]($rawPtr + ($Va - $start))
        }
    }
    throw ("VA 0x{0:X8} not in a PE section" -f $Va)
}

if (-not (Test-Path -LiteralPath $ExePath)) { throw "File not found: $ExePath" }

$bytes = [IO.File]::ReadAllBytes($ExePath)
$va = [uint32]0x004230A6
$offset = Convert-VaToFileOffset $bytes $va
$len = 30

$expected = [byte[]]@(
    0x68,0x00,0x03,0x00,0x00,
    0x68,0x00,0x04,0x00,0x00,
    0x8B,0x55,0xFC,
    0x8B,0x82,0x0C,0x03,0x00,0x00,
    0x50,
    0xB9,0xD0,0x94,0x06,0x01,
    0xE8,0x6C,0x86,0x0B,0x00
)

$current = New-Object byte[] $len
[Array]::Copy($bytes, $offset, $current, 0, $len)

$allNop = $true
for ($i = 0; $i -lt $len; $i++) { if ($current[$i] -ne 0x90) { $allNop = $false; break } }
if ($allNop) {
    Write-Host "Already patched: post-game ResolutionChange is NOPped." -ForegroundColor Yellow
    return
}

for ($i = 0; $i -lt $len; $i++) {
    if ($current[$i] -ne $expected[$i]) {
        $hex = ($current | ForEach-Object { "{0:X2}" -f $_ }) -join " "
        throw "Unexpected bytes at VA 0x$('{0:X8}' -f $va) (file 0x$('{0:X}' -f $offset)): $hex"
    }
}

$backup = "$ExePath.bak_postgameres_$(Get-Date -Format yyyyMMdd_HHmmss)"
[IO.File]::WriteAllBytes($backup, $bytes)
for ($i = 0; $i -lt $len; $i++) { $bytes[$offset + $i] = 0x90 }
[IO.File]::WriteAllBytes($ExePath, $bytes)

Write-Host "Patched: skipped post-game ResolutionChange (no DirectDraw re-init crash)." -ForegroundColor Green
Write-Host "Backup: $backup"
