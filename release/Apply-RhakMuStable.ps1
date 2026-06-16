param(
    [string]$GameDir = "C:\Program Files (x86)\TriggerSoft\RhakMu"
)

# Applies the STABLE RhakMu client patch set to a fresh install.
# Stable = login / lobby / channel / room / matchmaking / game-entry all work,
# and the game returns toward the menu at match-end without crashing.
# (The experimental RoomNetMGR-coordination patch is intentionally NOT applied
#  here -- it is still under investigation.)
#
# Run as Administrator. Close the game first.

$ErrorActionPreference = "Stop"
$exe = Join-Path $GameDir "Rhakmu.exe"
if (-not (Test-Path -LiteralPath $exe)) { throw "Rhakmu.exe not found: $exe" }

$root = Split-Path -Parent $MyInvocation.MyCommand.Path

$running = Get-Process -Name "Rhakmu" -ErrorAction SilentlyContinue
if ($running) { throw "Rhakmu.exe is running. Close the game first." }

# one-time full backup of the fresh exe
$baseBak = "$exe.bak_freshinstall"
if (-not (Test-Path $baseBak)) { Copy-Item $exe $baseBak; Write-Host "Saved fresh-install backup: $baseBak" -ForegroundColor Cyan }

$steps = @(
    @{ Name="Battle start sync";        Script="Patch-RhakMuBattleStartSync.ps1";        Args=@{ SeedMode="Zero" } },
    @{ Name="Menu delete guards";       Script="Patch-RhakMuMenuDeleteGuards.ps1";        Args=@{} },
    @{ Name="Panel menu guards";        Script="Patch-RhakMuPanelMenuGuards.ps1";         Args=@{} },
    @{ Name="DirectDraw restore guard"; Script="Patch-RhakMuIcarusRestoreGuard.ps1";      Args=@{} },
    @{ Name="Room send guards";         Script="Patch-RhakMuRoomSendGuards.ps1";          Args=@{} },
    @{ Name="Post-game resolution guard"; Script="Patch-RhakMuPostGameResolutionGuard.ps1"; Args=@{} },
    @{ Name="Post-game result-form guard"; Script="Patch-RhakMuPostGameFormGuard.ps1";    Args=@{} },
    @{ Name="Menu mouse-cursor crash guard"; Script="Patch-RhakMuMenuMouseGuard.ps1";     Args=@{} },
    @{ Name="Guest P2P sync (countdown)";   Script="Patch-RhakMuGuestP2PSync.ps1";        Args=@{} },
    @{ Name="In-game P2P timeout (60s)";   Script="Patch-RhakMuInGameTimeout.ps1";       Args=@{} },
    @{ Name="DP8 timeout draw fix";        Script="Patch-RhakMuDP8Timeout.ps1";          Args=@{} },
    @{ Name="DP8 draw triggers (A/B/C)"; Script="Patch-RhakMuDP8DrawTriggers.ps1";     Args=@{} }
)

# handes.dll (anti-cheat) patch -- different target file, handled separately below.

foreach ($s in $steps) {
    Write-Host ""
    Write-Host "==> $($s.Name)" -ForegroundColor Cyan
    $path = Join-Path $root $s.Script
    if (-not (Test-Path $path)) { throw "Missing patch script: $path" }
    $a = $s.Args.Clone(); $a["ExePath"] = $exe
    & $path @a
}

Write-Host ""
Write-Host "==> HanGame anti-cheat (handes.dll) guard" -ForegroundColor Cyan
$hd = Join-Path $root "Patch-RhakMuHanDesGuard.ps1"
$dll = Join-Path $GameDir "handes.dll"
if ((Test-Path $hd) -and (Test-Path $dll)) { & $hd -DllPath $dll }
else { Write-Host "  (handes.dll or patch script missing, skipped)" -ForegroundColor Yellow }

Write-Host ""
Write-Host "Stable patch set applied to $exe" -ForegroundColor Green
Write-Host "Start the lobby server, then log in and test rooms." -ForegroundColor Cyan
