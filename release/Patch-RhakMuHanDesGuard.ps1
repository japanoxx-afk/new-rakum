param(
    [string]$DllPath = "C:\Program Files (x86)\TriggerSoft\RhakMu\handes.dll",
    [switch]$Revert
)

# HanDes.dll is the HanGame anti-cheat module. Its _DllMainCRTStartup runs a
# per-thread callback (pRawDllMain at [0x1001ED2C]) via "call eax" at
# RVA 0x30C8, on EVERY thread attach. At in-game entry the NVIDIA driver
# (nvd3dum) spawns threads, the anti-cheat callback runs and crashes with a
# heap fault (HanDes EncryptFunc -> ntdll) -> the whole game dies.
#
# A private server doesn't need the anti-cheat. This NOPs the "call eax"
# (FF D0 -> 90 90) so the per-thread anti-cheat callback never runs. eax is
# left as the (non-null) callback pointer, so the following "test eax,eax;
# je" check still passes and normal CRT/DllMain flow continues. The game's
# real DecryptFunc init (DllMain PROCESS_ATTACH) is untouched.

$ErrorActionPreference = "Stop"
if (-not (Test-Path -LiteralPath $DllPath)) { throw "File not found: $DllPath" }
$bytes = [IO.File]::ReadAllBytes($DllPath)

$off  = 0x30C8
$orig = [byte[]]@(0xFF,0xD0)   # call eax
$nop  = [byte[]]@(0x90,0x90)

function Eq($a,$o,$e){ for($i=0;$i -lt $e.Length;$i++){ if($a[$o+$i] -ne $e[$i]){ return $false } } return $true }

if ($Revert) {
    if (Eq $bytes $off $nop) { $bytes[$off]=0xFF; $bytes[$off+1]=0xD0; [IO.File]::WriteAllBytes($DllPath,$bytes); Write-Host "Reverted HanDes guard." -ForegroundColor Green }
    else { Write-Host "Not patched." -ForegroundColor Yellow }
    return
}

if (Eq $bytes $off $nop) { Write-Host "Already patched: HanDes per-thread anti-cheat callback NOPped." -ForegroundColor Yellow; return }
if (-not (Eq $bytes $off $orig)) {
    $h=($bytes[$off..($off+1)]|%{ "{0:X2}" -f $_ }) -join " "; throw "Unexpected bytes at 0x$('{0:X}' -f $off): $h"
}
[IO.File]::WriteAllBytes("$DllPath.bak_handesguard_$(Get-Date -Format yyyyMMdd_HHmmss)", $bytes)
$bytes[$off]=0x90; $bytes[$off+1]=0x90
[IO.File]::WriteAllBytes($DllPath, $bytes)
Write-Host "Patched: neutralized HanDes per-thread anti-cheat callback (no in-game-entry crash)." -ForegroundColor Green
