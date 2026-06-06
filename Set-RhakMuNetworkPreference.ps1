param(
    [switch]$DisableVirtualAdapters,
    [switch]$RestoreVirtualAdapters,
    [switch]$PreferRadminSource,
    [switch]$RestoreSourcePreference,
    [switch]$ShowOnly
)

$ErrorActionPreference = "Stop"

function Test-IsAdministrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Get-ScriptRoot {
    if ($PSScriptRoot) { return $PSScriptRoot }
    return Split-Path -Parent $MyInvocation.MyCommand.Path
}

$root = Get-ScriptRoot
$statePath = Join-Path $root "rhakmu_disabled_virtual_adapters.json"
$sourceStatePath = Join-Path $root "rhakmu_source_preference_state.json"
$virtualPattern = "VMware|VirtualBox|VMnet|Host-Only|Hyper-V|vEthernet|WSL|Npcap Loopback"
$radminPattern = "Radmin|Famatech"

if ($RestoreSourcePreference) {
    if (-not (Test-IsAdministrator)) {
        throw "Run this script from an elevated PowerShell window to restore source-address preferences."
    }

    if (-not (Test-Path -LiteralPath $sourceStatePath)) {
        Write-Host "No saved source-preference state found: $sourceStatePath" -ForegroundColor Yellow
        exit 0
    }

    $savedSource = Get-Content -LiteralPath $sourceStatePath -Raw | ConvertFrom-Json
    foreach ($item in @($savedSource)) {
        $ip = Get-NetIPAddress -InterfaceIndex $item.InterfaceIndex -IPAddress $item.IPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue
        if ($ip) {
            Write-Host "Restoring SkipAsSource=$($item.SkipAsSource) for $($item.IPAddress) on ifIndex $($item.InterfaceIndex)" -ForegroundColor Cyan
            Set-NetIPAddress -InterfaceIndex $item.InterfaceIndex -IPAddress $item.IPAddress -SkipAsSource ([bool]$item.SkipAsSource) -ErrorAction SilentlyContinue
        }
    }
    Write-Host "Source-address preference restore completed." -ForegroundColor Green
    exit 0
}

if ($RestoreVirtualAdapters) {
    if (-not (Test-IsAdministrator)) {
        throw "Run this script from an elevated PowerShell window to restore network adapters."
    }

    if (-not (Test-Path -LiteralPath $statePath)) {
        Write-Host "No saved disabled-adapter state found: $statePath" -ForegroundColor Yellow
        exit 0
    }

    $saved = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
    foreach ($item in @($saved)) {
        $adapter = Get-NetAdapter -Name $item.Name -ErrorAction SilentlyContinue
        if ($adapter -and $adapter.Status -eq "Disabled") {
            Write-Host "Enabling adapter: $($adapter.Name)" -ForegroundColor Cyan
            Enable-NetAdapter -Name $adapter.Name -Confirm:$false
        }
    }
    Write-Host "Virtual adapter restore completed." -ForegroundColor Green
    exit 0
}

$adapters = Get-NetAdapter -ErrorAction Stop |
    Sort-Object -Property @{ Expression = { if ($_.InterfaceDescription -match $radminPattern -or $_.Name -match $radminPattern) { 0 } else { 1 } } }, Name

$adapterInfo = foreach ($adapter in $adapters) {
    $ipObjects = @(Get-NetIPAddress -InterfaceIndex $adapter.InterfaceIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.IPAddress -notlike "169.254.*" } |
        Select-Object IPAddress, SkipAsSource)
    $ips = @($ipObjects | Select-Object -ExpandProperty IPAddress)
    $ipIf = Get-NetIPInterface -InterfaceIndex $adapter.InterfaceIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue
    [pscustomobject]@{
        Name = $adapter.Name
        Description = $adapter.InterfaceDescription
        Status = $adapter.Status
        InterfaceIndex = $adapter.InterfaceIndex
        IPv4 = ($ips -join ",")
        Metric = if ($ipIf) { $ipIf.InterfaceMetric } else { $null }
        AutomaticMetric = if ($ipIf) { $ipIf.AutomaticMetric } else { $null }
        SkipAsSource = (($ipObjects | ForEach-Object { "$($_.IPAddress):$($_.SkipAsSource)" }) -join ",")
        IsRadmin = ($adapter.Name -match $radminPattern -or $adapter.InterfaceDescription -match $radminPattern -or ($ips | Where-Object { $_ -like "26.*" }))
        IsVirtualConflict = ($adapter.Name -match $virtualPattern -or $adapter.InterfaceDescription -match $virtualPattern)
    }
}

Write-Host ""
Write-Host "RhakMu network adapters" -ForegroundColor Cyan
$adapterInfo | Format-Table -AutoSize Name,Status,IPv4,Metric,AutomaticMetric,SkipAsSource,IsRadmin,IsVirtualConflict,Description

if ($ShowOnly) {
    exit 0
}

if (-not (Test-IsAdministrator)) {
    throw "Run this script from an elevated PowerShell window. Network interface metrics need administrator rights."
}

$radmin = @($adapterInfo | Where-Object { $_.IsRadmin -and $_.Status -eq "Up" } | Select-Object -First 1)
if ($radmin.Count -eq 0) {
    Write-Host "Radmin VPN adapter was not detected. Install/connect Radmin VPN first, then run this script again." -ForegroundColor Yellow
} else {
    foreach ($item in $radmin) {
        Write-Host "Setting Radmin adapter metric to 5: $($item.Name) [$($item.IPv4)]" -ForegroundColor Cyan
        Set-NetIPInterface -InterfaceIndex $item.InterfaceIndex -AddressFamily IPv4 -AutomaticMetric Disabled -InterfaceMetric 5
    }
}

$virtualAdapters = @($adapterInfo | Where-Object { $_.IsVirtualConflict -and -not $_.IsRadmin })
foreach ($item in $virtualAdapters) {
    Write-Host "Setting virtual adapter metric to 900: $($item.Name) [$($item.IPv4)]" -ForegroundColor DarkCyan
    Set-NetIPInterface -InterfaceIndex $item.InterfaceIndex -AddressFamily IPv4 -AutomaticMetric Disabled -InterfaceMetric 900 -ErrorAction SilentlyContinue
}

if ($PreferRadminSource) {
    $radminUp = @($adapterInfo | Where-Object { $_.IsRadmin -and $_.Status -eq "Up" })
    if ($radminUp.Count -eq 0) {
        Write-Host "Radmin VPN adapter was not detected; source-address preference was not changed." -ForegroundColor Yellow
    } else {
        $allIps = @(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
            Where-Object {
                $_.IPAddress -notlike "127.*" -and
                $_.IPAddress -notlike "169.254.*" -and
                $_.IPAddress -ne "0.0.0.0"
            })

        $sourceState = foreach ($ip in $allIps) {
            [pscustomobject]@{
                InterfaceIndex = $ip.InterfaceIndex
                IPAddress = $ip.IPAddress
                SkipAsSource = [bool]$ip.SkipAsSource
            }
        }
        $sourceState | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath $sourceStatePath -Encoding UTF8

        foreach ($ip in $allIps) {
            $isRadminIp = ($ip.IPAddress -like "26.*")
            $targetSkip = -not $isRadminIp
            Write-Host "Setting SkipAsSource=$targetSkip for $($ip.IPAddress) on ifIndex $($ip.InterfaceIndex)" -ForegroundColor Cyan
            Set-NetIPAddress -InterfaceIndex $ip.InterfaceIndex -IPAddress $ip.IPAddress -SkipAsSource $targetSkip -ErrorAction SilentlyContinue
        }
        Write-Host "Saved source-preference state: $sourceStatePath" -ForegroundColor Green
    }
}

if ($DisableVirtualAdapters) {
    $targets = @($virtualAdapters | Where-Object { $_.Status -eq "Up" })
    if ($targets.Count -eq 0) {
        Write-Host "No active VMware/VirtualBox/Hyper-V style adapters found to disable." -ForegroundColor Yellow
    } else {
        $targets | Select-Object Name,Description,InterfaceIndex,IPv4 |
            ConvertTo-Json -Depth 3 |
            Set-Content -LiteralPath $statePath -Encoding UTF8

        foreach ($item in $targets) {
            Write-Host "Disabling virtual adapter for RhakMu test: $($item.Name) [$($item.IPv4)]" -ForegroundColor Yellow
            Disable-NetAdapter -Name $item.Name -Confirm:$false
        }
        Write-Host "Saved disabled-adapter state: $statePath" -ForegroundColor Green
    }
}

Write-Host ""
Write-Host "RhakMu network preference completed. Restart RhakMu after changing adapters." -ForegroundColor Green
Write-Host "If virtual adapters were disabled, restore them later with:" -ForegroundColor Gray
Write-Host "powershell -NoProfile -ExecutionPolicy Bypass -File .\Set-RhakMuNetworkPreference.ps1 -RestoreVirtualAdapters" -ForegroundColor Gray
Write-Host "If Radmin source preference was changed, restore it later with:" -ForegroundColor Gray
Write-Host "powershell -NoProfile -ExecutionPolicy Bypass -File .\Set-RhakMuNetworkPreference.ps1 -RestoreSourcePreference" -ForegroundColor Gray
