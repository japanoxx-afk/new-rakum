param(
    [string]$ExePath = "C:\Program Files (x86)\TriggerSoft\RhakMu\Rhakmu.exe",
    [int]$Latency = 2,
    [switch]$Revert
)

# RTS input lag = lockstep command latency. The engine schedules issued orders to
# execute N "sync turns" in the future (to mask network round-trip). Even vs the AI,
# matches go through the room/DP8 path = Game_Multi, which sets the latency to 4:
#
#   Game_Single  @ 0x004D7921 : mov word [net+0x48], 1   (m_nLatencySyncCount = 1)
#   Game_Multi   @ 0x004D7ABA : mov word [net+0x48], 4   <-- this one, the live path
#   Game_Replay  @ 0x004D7CDE : mov word [net+0x48], 4   (left as-is: replay sync)
#
# net manager = [0x00B411A4]; member +0x48 = m_nLatencySyncCount (from Rhakmu.000 PDB).
# Lowering 4 -> N cuts click-to-response by ~ (4-N)/4. N=2 halves the lag and still
# tolerates normal/VPN ping; N=1 = minimum (LAN/local/AI only, least ping tolerance);
# N=3 = mild cut for higher-ping multiplayer.
#
# NOTE (multiplayer): both peers MUST run the same N, and the network round-trip must
# fit within N * (turn interval). For internet MP keep N>=2; for LAN/AI N=1 is fine.

$ErrorActionPreference = "Stop"
if (-not (Test-Path -LiteralPath $ExePath)) { throw "File not found: $ExePath" }
if ($Latency -lt 1 -or $Latency -gt 4) { throw "Latency must be 1..4 (got $Latency)" }

$IMM_OFF = 0x000D7ABE          # file offset of the imm8 in `mov word [eax+0x48], 4`
$INSTR   = [byte[]]@(0x66,0xC7,0x40,0x48)   # mov word ptr [eax+0x48], imm16
$INSTR_OFF = 0x000D7ABA

$bytes = [IO.File]::ReadAllBytes($ExePath)

# sanity: the instruction prefix must match (guards against wrong/patched-elsewhere exe)
for ($i = 0; $i -lt $INSTR.Length; $i++) {
    if ($bytes[$INSTR_OFF + $i] -ne $INSTR[$i]) {
        $h = ($bytes[$INSTR_OFF..($INSTR_OFF+5)] | % { "{0:X2}" -f $_ }) -join " "
        throw "Game_Multi latency instruction not found at 0x$('{0:X}' -f $INSTR_OFF) (got $h). Wrong exe/version?"
    }
}

$cur = $bytes[$IMM_OFF]
$target = if ($Revert) { 4 } else { $Latency }

if ($cur -eq $target) {
    Write-Host "Already set: Game_Multi latency = $target sync turns." -ForegroundColor Yellow
    return
}

$stamp = Get-Date -Format yyyyMMdd_HHmmss
[IO.File]::WriteAllBytes("$ExePath.bak_latency_$stamp", $bytes)
$bytes[$IMM_OFF] = [byte]$target
[IO.File]::WriteAllBytes($ExePath, $bytes)

if ($Revert) {
    Write-Host "Reverted: Game_Multi latency restored to 4 (was $cur)." -ForegroundColor Green
} else {
    Write-Host "Patched: Game_Multi command latency $cur -> $target sync turns." -ForegroundColor Green
    Write-Host "  Lower = snappier; multiplayer needs both peers identical + ping within budget." -ForegroundColor DarkGray
}
