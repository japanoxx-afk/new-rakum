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

function Patch-Nops([byte[]]$Bytes, [uint32]$Va, [byte[]]$Expected, [string]$Name) {
    $fileOff = Convert-VaToFileOffset $Bytes $Va
    $actual = $Bytes[$fileOff..($fileOff + $Expected.Length - 1)]
    $same = $true
    for ($i = 0; $i -lt $Expected.Length; $i++) {
        if ($actual[$i] -ne $Expected[$i]) {
            $same = $false
            break
        }
    }

    $alreadyPatched = $true
    for ($i = 0; $i -lt $Expected.Length; $i++) {
        if ($actual[$i] -ne 0x90) {
            $alreadyPatched = $false
            break
        }
    }

    if (-not $same -and -not $alreadyPatched) {
        $hex = ($actual | ForEach-Object { "{0:X2}" -f $_ }) -join " "
        throw "$Name unexpected bytes at VA 0x$('{0:X8}' -f $Va): $hex"
    }

    for ($i = 0; $i -lt $Expected.Length; $i++) {
        $Bytes[$fileOff + $i] = 0x90
    }

    Write-Host "$Name patched at VA 0x$('{0:X8}' -f $Va), file offset 0x$('{0:X}' -f $fileOff)"
}

$bytes = [IO.File]::ReadAllBytes($ExePath)
$backup = "$ExePath.bak_menudelete_$(Get-Date -Format yyyyMMdd_HHmmss)"
[IO.File]::WriteAllBytes($backup, $bytes)
Write-Host "Backup: $backup"

$channelDeleteBlock = [byte[]]@(0x8B,0x4D,0xFC,0x51,0xE8,0x67,0xE4,0x0B,0x00,0x83,0xC4,0x04)
$guildDeleteBlock = [byte[]]@(0x8B,0x4D,0xFC,0x51,0xE8,0x07,0xD8,0x0B,0x00,0x83,0xC4,0x04)

# The scalar deleting destructors call the real destructor first and then
# operator delete. Older crashes showed the operator delete path corrupting
# the small-block heap, so keep it disabled.
Patch-Nops $bytes 0x0041E2AE $channelDeleteBlock "CScenChannel scalar-delete operator delete"
Patch-Nops $bytes 0x0041EF0E $guildDeleteBlock "CScenGuild scalar-delete operator delete"

# In dummy-server mode, returning from an active game can leave the channel or
# guild scene form controls already torn down. The real destructors then call
# the GameCtrl form cleanup again and can crash in DeleteAllControls/OnChar.
# Skip only that inherited form cleanup call; the object memory itself is
# already protected by the scalar-delete patches above.
$channelFormCleanupBlock = [byte[]]@(0x8B,0x4D,0xFC,0xE8,0x33,0x28,0xFF,0xFF)
$guildFormCleanupBlock = [byte[]]@(0x8B,0x4D,0xFC,0xE8,0xD3,0x1B,0xFF,0xFF)
Patch-Nops $bytes 0x0041E2E5 $channelFormCleanupBlock "CScenChannel destructor form cleanup"
Patch-Nops $bytes 0x0041EF45 $guildFormCleanupBlock "CScenGuild destructor form cleanup"

[IO.File]::WriteAllBytes($ExePath, $bytes)
Write-Host "Done."
