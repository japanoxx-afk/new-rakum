param(
    [string]$ExePath = "C:\Program Files (x86)\TriggerSoft\RhakMu\Rhakmu.exe"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $ExePath)) {
    throw "File not found: $ExePath"
}

$bytes = [IO.File]::ReadAllBytes($ExePath)

function Test-BytesEqual([byte[]]$A, [byte[]]$B) {
    if ($A.Length -ne $B.Length) { return $false }
    for ($i = 0; $i -lt $A.Length; $i++) {
        if ($A[$i] -ne $B[$i]) { return $false }
    }
    return $true
}

function Apply-PatchBytes(
    [byte[]]$Image,
    [int]$Offset,
    [byte[]]$Expected,
    [byte[]]$Patch,
    [string]$Name
) {
    if ($Expected.Length -ne $Patch.Length) {
        throw "$Name patch length mismatch."
    }

    $current = New-Object byte[] $Expected.Length
    [Array]::Copy($Image, $Offset, $current, 0, $current.Length)

    if (Test-BytesEqual $current $Patch) {
        Write-Host "Already patched: $Name" -ForegroundColor Yellow
        return $false
    }

    if (-not (Test-BytesEqual $current $Expected)) {
        $cur = ($current | ForEach-Object { "{0:X2}" -f $_ }) -join " "
        throw "Unexpected bytes for $Name at offset 0x$($Offset.ToString('X')). Current: $cur"
    }

    [Array]::Copy($Patch, 0, $Image, $Offset, $Patch.Length)
    Write-Host "Patched: $Name" -ForegroundColor Green
    return $true
}

function Apply-AnyExpectedPatchBytes(
    [byte[]]$Image,
    [int]$Offset,
    [byte[][]]$ExpectedList,
    [byte[]]$Patch,
    [string]$Name
) {
    foreach ($expected in $ExpectedList) {
        if ($expected.Length -ne $Patch.Length) {
            throw "$Name patch length mismatch."
        }
    }

    $current = New-Object byte[] $Patch.Length
    [Array]::Copy($Image, $Offset, $current, 0, $current.Length)

    if (Test-BytesEqual $current $Patch) {
        Write-Host "Already patched: $Name" -ForegroundColor Yellow
        return $false
    }

    foreach ($expected in $ExpectedList) {
        if (Test-BytesEqual $current $expected) {
            [Array]::Copy($Patch, 0, $Image, $Offset, $Patch.Length)
            Write-Host "Patched: $Name" -ForegroundColor Green
            return $true
        }
    }

    $cur = ($current | ForEach-Object { "{0:X2}" -f $_ }) -join " "
    throw "Unexpected bytes for $Name at offset 0x$($Offset.ToString('X')). Current: $cur"
}

$changed = $false

# Guard classRoomNetMGR::RMPKSend_GameOption at VA 0x0044577C.
# Room option buttons update local option flags before calling this function.
# If the room-net send buffer is absent, skip only the broadcast packet.
$changed = (Apply-PatchBytes `
    -Image $bytes `
    -Offset 0x4577C `
    -Name "RMPKSend_GameOption null send-buffer guard" `
    -Expected ([byte[]]@(
        0x8B,0x45,0xFC,
        0x8B,0x48,0x04,
        0x8B,0x51,0x0C,
        0x66,0xC7,0x02,0x11,0x10
    )) `
    -Patch ([byte[]]@(
        # mov eax, [ebp-4]
        0x8B,0x45,0xFC,
        # cmp dword ptr [eax+4], 0
        0x83,0x78,0x04,0x00,
        # je 0x0044595D
        0x0F,0x84,0xD4,0x01,0x00,0x00,
        # nop
        0x90
    ))) -or $changed

# Guard classRoomNetMGR::RMPKSend_GameStart at VA 0x00445AEC.
# The OK/start button can call this before RoomNetMGR::Init created the send
# buffer. In dummy-server mode, skip the outbound room-net packet but still
# execute the local "game start" state transition at the end of the function.
$changed = (Apply-AnyExpectedPatchBytes `
    -Image $bytes `
    -Offset 0x45AEC `
    -Name "RMPKSend_GameStart null send-buffer guard" `
    -ExpectedList ([byte[][]]@(
        [byte[]]@(
            0x8B,0x45,0xFC,
            0x8B,0x48,0x04,
            0x8B,0x51,0x0C,
            0x66,0xC7,0x02,0x0A,0x10
        ),
        [byte[]]@(
            0x8B,0x45,0xFC,
            0x83,0x78,0x04,0x00,
            0x0F,0x84,0xBF,0x00,0x00,0x00,
            0x90
        )
    )) `
    -Patch ([byte[]]@(
        # mov eax, [ebp-4]
        0x8B,0x45,0xFC,
        # cmp dword ptr [eax+4], 0
        0x83,0x78,0x04,0x00,
        # je 0x00445BB1
        0x0F,0x84,0xB8,0x00,0x00,0x00,
        # nop
        0x90
    ))) -or $changed

# Guard classRoomNetMGR::RMPKSend_UserLeft at VA 0x00445BFC.
# Original dereferences this+4 immediately. If RoomNetMGR::Init was not called,
# this+4 is null and room exit crashes. Return before touching the send buffer.
$changed = (Apply-AnyExpectedPatchBytes `
    -Image $bytes `
    -Offset 0x45BFC `
    -Name "RMPKSend_UserLeft null send-buffer guard" `
    -ExpectedList ([byte[][]]@(
        [byte[]]@(
            0x8B,0x45,0xFC,
            0x8B,0x48,0x04,
            0x8B,0x51,0x0C,
            0x66,0xC7,0x02,0x08,0x10
        ),
        [byte[]]@(
            0x8B,0x45,0xFC,
            0x83,0x78,0x04,0x00,
            0x0F,0x84,0xBB,0x00,0x00,0x00,
            0x90
        )
    )) `
    -Patch ([byte[]]@(
        # mov eax, [ebp-4]
        0x8B,0x45,0xFC,
        # cmp dword ptr [eax+4], 0
        0x83,0x78,0x04,0x00,
        # je 0x00445CC6
        0x0F,0x84,0xBD,0x00,0x00,0x00,
        # nop
        0x90
    ))) -or $changed

if ($changed) {
    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $backupPath = "$ExePath.bak_roomguards_$stamp"
    Copy-Item -LiteralPath $ExePath -Destination $backupPath
    [IO.File]::WriteAllBytes($ExePath, $bytes)
    Write-Host "Wrote patched executable." -ForegroundColor Green
    Write-Host "Backup: $backupPath"
} else {
    Write-Host "No changes written."
}
