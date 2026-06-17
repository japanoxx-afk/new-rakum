param(
    [string]$ExePath = "C:\Program Files (x86)\TriggerSoft\RhakMu\Rhakmu.exe",
    [int]$Latency = 2,
    [switch]$Revert
)

# RTS input lag = lockstep command latency. The engine schedules issued orders to
# execute N "sync turns" in the future (to mask network round-trip). Even vs the AI,
# matches go through the room/DP8 path = Game_Multi, which defaults the latency to 4.
#
# Three init sites set m_nLatencySyncCount (net manager + member 0x48), each:
#   mov eax, [net_global] ; mov word [eax+0x48], <N> ; call <game_init>
# Sorted by address they are: Game_Single (1), Game_Multi (4), Game_Replay (4).
# We patch the MIDDLE one (Game_Multi = the live MP + vs-AI path); Single already
# minimal, Replay left as-is (replay determinism). The sites are located by the byte
# signature `66 C7 40 48 ?? 00 E8`, so this works across game builds (offsets vary).
#
# N=2 halves the click-to-response lag and still tolerates normal/VPN ping;
# N=1 = minimum (LAN/local/AI; least ping tolerance); N=3 = milder cut for high-ping MP.
# MULTIPLAYER: both peers MUST run the same N, and round-trip must fit N*turn-interval.

$ErrorActionPreference = "Stop"
if (-not (Test-Path -LiteralPath $ExePath)) { throw "File not found: $ExePath" }
if ($Latency -lt 1 -or $Latency -gt 4) { throw "Latency must be 1..4 (got $Latency)" }

$bytes = [IO.File]::ReadAllBytes($ExePath)

# locate sites: 66 C7 40 48 <imm8> 00 E8   (mov word [eax+0x48], imm ; call rel32)
$sites = @()
for ($i = 0; $i -lt $bytes.Length - 7; $i++) {
    if ($bytes[$i] -eq 0x66 -and $bytes[$i+1] -eq 0xC7 -and $bytes[$i+2] -eq 0x40 -and
        $bytes[$i+3] -eq 0x48 -and $bytes[$i+5] -eq 0x00 -and $bytes[$i+6] -eq 0xE8) {
        $sites += $i
    }
}
if ($sites.Count -ne 3) {
    throw "Expected 3 latency init sites (Single/Multi/Replay), found $($sites.Count). Unknown build?"
}
$sites = $sites | Sort-Object
$multiInstr = $sites[1]      # middle site = Game_Multi
$immOff = $multiInstr + 4    # the imm8 byte

$cur = $bytes[$immOff]
$target = if ($Revert) { 4 } else { $Latency }

Write-Host ("Sites: Single@0x{0:X} Multi@0x{1:X}(={3}) Replay@0x{2:X}" -f $sites[0],$sites[1],$sites[2],$cur)

if ($cur -eq $target) {
    Write-Host "Already set: Game_Multi latency = $target sync turns." -ForegroundColor Yellow
    return
}

$stamp = Get-Date -Format yyyyMMdd_HHmmss
[IO.File]::WriteAllBytes("$ExePath.bak_latency_$stamp", $bytes)
$bytes[$immOff] = [byte]$target
[IO.File]::WriteAllBytes($ExePath, $bytes)

if ($Revert) {
    Write-Host "Reverted: Game_Multi latency restored to 4 (was $cur)." -ForegroundColor Green
} else {
    Write-Host "Patched: Game_Multi command latency $cur -> $target sync turns." -ForegroundColor Green
    Write-Host "  Multiplayer: apply the SAME value on both PCs." -ForegroundColor DarkGray
}
