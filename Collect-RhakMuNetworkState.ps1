param(
    [string]$OutputDir = ".\rhakmu_network_state",
    [int]$Port = 11223,
    [string]$LocalIp = "",
    [string]$PeerIp = ""
)

$ErrorActionPreference = "Stop"

function ConvertTo-SafeName([string]$Text) {
    if ([string]::IsNullOrWhiteSpace($Text)) { return "unknown" }
    return (($Text.Trim() -replace '[\\/:*?"<>|,=\s]+', "_") -replace "_+", "_").Trim("_")
}

function Get-RhakMuLocalIp {
    if (-not [string]::IsNullOrWhiteSpace($LocalIp)) { return $LocalIp.Trim() }

    try {
        $addresses = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction Stop |
            Where-Object {
                $_.IPAddress -notlike "127.*" -and
                $_.IPAddress -notlike "169.254.*" -and
                $_.IPAddress -ne "0.0.0.0"
            }

        $radmin = $addresses | Where-Object { $_.IPAddress -like "26.*" } | Select-Object -First 1
        if ($null -ne $radmin) { return $radmin.IPAddress }

        $preferred = $addresses | Select-Object -First 1
        if ($null -ne $preferred) { return $preferred.IPAddress }
    } catch {}

    return "unknown-ip"
}

function Write-Section([string]$Path, [string]$Title, [scriptblock]$Body) {
    Add-Content -LiteralPath $Path -Encoding UTF8 -Value ""
    Add-Content -LiteralPath $Path -Encoding UTF8 -Value "===== $Title ====="
    try {
        $result = & $Body | Out-String -Width 240
        if ([string]::IsNullOrWhiteSpace($result)) { $result = "(no output)`r`n" }
        Add-Content -LiteralPath $Path -Encoding UTF8 -Value $result.TrimEnd()
    } catch {
        Add-Content -LiteralPath $Path -Encoding UTF8 -Value "ERROR: $($_.Exception.Message)"
    }
}

$resolvedOutputDir = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($OutputDir)
New-Item -ItemType Directory -Force -Path $resolvedOutputDir | Out-Null

$localIpValue = Get-RhakMuLocalIp
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$safeIp = ConvertTo-SafeName $localIpValue
$statePath = Join-Path $resolvedOutputDir "rhakmu_network_state_${safeIp}_$stamp.txt"

@(
    "Collected: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss.fff')",
    "Computer: $env:COMPUTERNAME",
    "LocalIp: $localIpValue",
    "PeerIp: $PeerIp",
    "Port: $Port"
) | Set-Content -LiteralPath $statePath -Encoding UTF8

Write-Section $statePath "UDP endpoint on RhakMu port" {
    Get-NetUDPEndpoint -LocalPort $Port -ErrorAction SilentlyContinue |
        Select-Object LocalAddress, LocalPort, OwningProcess,
            @{Name = "Process"; Expression = { (Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue).ProcessName } } |
        Format-Table -AutoSize
}

Write-Section $statePath "Rhakmu process sockets" {
    $rhakmu = Get-Process -Name Rhakmu -ErrorAction SilentlyContinue
    if ($null -eq $rhakmu) {
        "Rhakmu process is not running."
    } else {
        $ids = $rhakmu.Id
        Get-NetUDPEndpoint -ErrorAction SilentlyContinue |
            Where-Object { $ids -contains $_.OwningProcess } |
            Select-Object LocalAddress, LocalPort, OwningProcess |
            Sort-Object LocalPort |
            Format-Table -AutoSize
    }
}

Write-Section $statePath "IPv4 interface priority" {
    Get-NetIPInterface -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Sort-Object InterfaceMetric, ifIndex |
        Format-Table ifIndex, InterfaceAlias, InterfaceMetric, NlMtu, ConnectionState, Dhcp -AutoSize
}

Write-Section $statePath "IPv4 addresses" {
    Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Sort-Object InterfaceAlias, IPAddress |
        Format-Table IPAddress, PrefixLength, InterfaceAlias, InterfaceIndex, AddressState -AutoSize
}

Write-Section $statePath "Route to peer" {
    if ([string]::IsNullOrWhiteSpace($PeerIp)) {
        "PeerIp was not supplied."
    } else {
        Find-NetRoute -RemoteIPAddress $PeerIp -ErrorAction SilentlyContinue |
            Select-Object InterfaceAlias, InterfaceIndex, NextHop, RouteMetric, InterfaceMetric, DestinationPrefix, SourceAddress |
            Format-Table -AutoSize
    }
}

Write-Section $statePath "IPv4 route table" {
    route print -4
}

Write-Section $statePath "Network adapters" {
    Get-NetAdapter -ErrorAction SilentlyContinue |
        Sort-Object ifIndex |
        Format-Table ifIndex, Name, InterfaceDescription, Status, MacAddress, LinkSpeed -AutoSize
}

Write-Section $statePath "Adapter bindings of interest" {
    Get-NetAdapterBinding -ErrorAction SilentlyContinue |
        Where-Object {
            $_.DisplayName -match 'Nprotect|TKFW|Npcap|Radmin|QoS|Internet Protocol|WFP|Filter|Firewall' -or
            $_.Name -match 'Radmin|Npcap'
        } |
        Sort-Object Name, DisplayName |
        Format-Table Name, DisplayName, ComponentID, Enabled -AutoSize
}

Write-Section $statePath "Network filter drivers of interest" {
    Get-CimInstance Win32_SystemDriver -ErrorAction SilentlyContinue |
        Where-Object {
            $_.Name -match 'TKFW|Nprotect|nProtect|Radmin|Npcap|WinDivert' -or
            $_.DisplayName -match 'TKFW|Nprotect|nProtect|Radmin|Npcap|WinDivert' -or
            $_.PathName -match 'TKFW|Nprotect|nProtect|Radmin|Npcap|WinDivert'
        } |
        Select-Object Name, DisplayName, State, StartMode, PathName |
        Format-List
}

Write-Section $statePath "Radmin and RhakMu related routes" {
    Get-NetRoute -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object {
            $_.DestinationPrefix -like '26.*' -or
            $_.InterfaceAlias -match 'Radmin|VPN|Ethernet|Wi-Fi'
        } |
        Sort-Object RouteMetric, InterfaceMetric, DestinationPrefix |
        Format-Table DestinationPrefix, NextHop, InterfaceAlias, InterfaceIndex, RouteMetric, Protocol -AutoSize
}

Write-Host "RhakMu network state saved: $statePath" -ForegroundColor Green
