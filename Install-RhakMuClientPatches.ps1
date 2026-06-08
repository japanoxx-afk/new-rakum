param(
    [string]$GameDir = "C:\Program Files (x86)\TriggerSoft\RhakMu",
    [switch]$SkipFirewall,
    [switch]$SkipGitPull,
    [switch]$SkipNetworkPreference,
    [switch]$DisableVirtualAdapters,
    [switch]$SkipBattleStartSyncPatch,
    [switch]$RestoreBattleStartSyncPatch,
    [ValidateSet("Zero", "Preserve")]
    [string]$BattleStartSeedMode = "Zero"
)

$ErrorActionPreference = "Stop"
$PatchBundleVersion = "2026-06-08.0011"

function Test-IsAdministrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Invoke-Step([string]$Name, [scriptblock]$Action) {
    Write-Host ""
    Write-Host "==> $Name" -ForegroundColor Cyan
    & $Action
    Write-Host "OK: $Name" -ForegroundColor Green
}

if (-not (Test-IsAdministrator)) {
    throw "Run this script from an elevated PowerShell window. RhakMu lives under Program Files and firewall rules also need administrator rights."
}

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $root

$runningGame = Get-Process -Name "Rhakmu" -ErrorAction SilentlyContinue
if ($runningGame) {
    $ids = ($runningGame | ForEach-Object { $_.Id }) -join ", "
    throw "Rhakmu.exe is running. Close the game first, then run this script again. Running process id(s): $ids"
}

if (-not $SkipGitPull -and (Test-Path -LiteralPath (Join-Path $root ".git"))) {
    Invoke-Step "GitHub latest files pull" {
        $git = Get-Command git -ErrorAction SilentlyContinue
        if ($null -eq $git) {
            $desktopGit = Join-Path $env:LOCALAPPDATA "GitHubDesktop\app-3.5.12\resources\app\git\cmd\git.exe"
            if (Test-Path -LiteralPath $desktopGit) {
                & $desktopGit pull origin main
            } else {
                Write-Host "git.exe not found. Skipping pull; existing local scripts will be used." -ForegroundColor Yellow
            }
        } else {
            & $git.Source pull origin main
        }
    }
}

if (-not $SkipFirewall) {
    Invoke-Step "Firewall rules" {
        & (Join-Path $root "Configure-RhakMuFirewall.ps1") -GameDir $GameDir
    }
}

if (-not $SkipNetworkPreference) {
    Invoke-Step "Radmin VPN network preference" {
        $networkArgs = @{}
        if ($DisableVirtualAdapters) {
            $networkArgs.DisableVirtualAdapters = $true
        }
        & (Join-Path $root "Set-RhakMuNetworkPreference.ps1") @networkArgs
    }
}

if ($RestoreBattleStartSyncPatch -and $SkipBattleStartSyncPatch) {
    throw "Use only one of -RestoreBattleStartSyncPatch or -SkipBattleStartSyncPatch."
}

if ($RestoreBattleStartSyncPatch) {
    Invoke-Step "Restore battle start sync client patch" {
        & (Join-Path $root "Restore-RhakMuBattleStartSync.ps1") -ExePath (Join-Path $GameDir "Rhakmu.exe")
    }
} elseif ($SkipBattleStartSyncPatch) {
    Invoke-Step "Battle start sync client patch skipped" {
        Write-Host "Battle start sync patch was not changed on this PC." -ForegroundColor Yellow
    }
} else {
    Invoke-Step "Battle start sync client patch" {
        & (Join-Path $root "Patch-RhakMuBattleStartSync.ps1") -ExePath (Join-Path $GameDir "Rhakmu.exe") -SeedMode $BattleStartSeedMode
    }
}

Invoke-Step "Menu delete guards" {
    & (Join-Path $root "Patch-RhakMuMenuDeleteGuards.ps1") -ExePath (Join-Path $GameDir "Rhakmu.exe")
}

Invoke-Step "Panel menu guards" {
    & (Join-Path $root "Patch-RhakMuPanelMenuGuards.ps1") -ExePath (Join-Path $GameDir "Rhakmu.exe")
}

Invoke-Step "DirectDraw restore guard" {
    & (Join-Path $root "Patch-RhakMuIcarusRestoreGuard.ps1") -ExePath (Join-Path $GameDir "Rhakmu.exe")
}

Invoke-Step "Post-game resolution-change crash guard" {
    & (Join-Path $root "Patch-RhakMuPostGameResolutionGuard.ps1") -ExePath (Join-Path $GameDir "Rhakmu.exe")
}

Invoke-Step "Final patch verification" {
    $verifyArgs = @{
        ExePath = (Join-Path $GameDir "Rhakmu.exe")
    }
    if ($RestoreBattleStartSyncPatch -or $SkipBattleStartSyncPatch) {
        $verifyArgs.AllowOriginalBattleStartSync = $true
        $verifyArgs.BattleStartSeedMode = "Any"
    } else {
        $verifyArgs.BattleStartSeedMode = $BattleStartSeedMode
    }
    & (Join-Path $root "Verify-RhakMuClientPatches.ps1") @verifyArgs
}

Write-Host ""
Write-Host "RhakMu client setup completed. Run this same script on every PC before testing multiplayer." -ForegroundColor Green
Write-Host "If room members are still removed after 10-20 seconds, rerun with -DisableVirtualAdapters on both PCs." -ForegroundColor Yellow
Write-Host "For start-sync A/B testing, run with -RestoreBattleStartSyncPatch on both PCs, then compare with the normal install." -ForegroundColor Yellow
Write-Host "Battle start seed mode: $BattleStartSeedMode" -ForegroundColor Cyan
Write-Host "RhakMu patch bundle version: $PatchBundleVersion" -ForegroundColor Cyan
