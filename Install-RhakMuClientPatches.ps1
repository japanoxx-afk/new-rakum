param(
    [string]$GameDir = "C:\Program Files (x86)\TriggerSoft\RhakMu",
    [switch]$SkipFirewall,
    [switch]$SkipGitPull,
    [switch]$SkipNetworkPreference,
    [switch]$DisableVirtualAdapters,
    [switch]$RadminOnly,
    [switch]$EnableFirewallProfiles
)

$ErrorActionPreference = "Stop"
$PatchBundleVersion = "2026-06-06.1645"

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
        $firewallArgs = @{
            GameDir = $GameDir
        }
        if ($RadminOnly) {
            $firewallArgs.RadminOnly = $true
        }
        if ($EnableFirewallProfiles) {
            $firewallArgs.EnableFirewallProfiles = $true
        }
        & (Join-Path $root "Configure-RhakMuFirewall.ps1") @firewallArgs
    }
}

if (-not $SkipNetworkPreference) {
    Invoke-Step "Radmin VPN network preference" {
        $networkArgs = @()
        if ($DisableVirtualAdapters) {
            $networkArgs += "-DisableVirtualAdapters"
        }
        if ($RadminOnly) {
            $networkArgs += "-PreferRadminSource"
        }
        & (Join-Path $root "Set-RhakMuNetworkPreference.ps1") @networkArgs
    }
}

Invoke-Step "Battle start sync client patch" {
    & (Join-Path $root "Patch-RhakMuBattleStartSync.ps1") -ExePath (Join-Path $GameDir "Rhakmu.exe")
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

Invoke-Step "Final patch verification" {
    & (Join-Path $root "Verify-RhakMuClientPatches.ps1") -ExePath (Join-Path $GameDir "Rhakmu.exe")
}

Write-Host ""
Write-Host "RhakMu client setup completed. Run this same script on every PC before testing multiplayer." -ForegroundColor Green
Write-Host "For Radmin-only multiplayer tests, run with -RadminOnly -EnableFirewallProfiles on every PC." -ForegroundColor Yellow
Write-Host "If room members are still removed after 10-20 seconds, rerun with -DisableVirtualAdapters on both PCs." -ForegroundColor Yellow
Write-Host "RhakMu patch bundle version: $PatchBundleVersion" -ForegroundColor Cyan
