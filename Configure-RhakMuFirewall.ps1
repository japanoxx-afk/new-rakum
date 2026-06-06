param(
    [string]$GameDir = "C:\Program Files (x86)\TriggerSoft\RhakMu",
    [string]$RemoteAddress = "Any",
    [switch]$RadminOnly,
    [switch]$EnableFirewallProfiles
)

$ErrorActionPreference = "Stop"

$exePath = Join-Path $GameDir "Rhakmu.exe"
if (-not (Test-Path -LiteralPath $exePath)) {
    throw "Rhakmu.exe not found: $exePath"
}

$launcherPath = Join-Path $GameDir "Launcher.exe"

$ports = @(
    "80",
    "11223",
    "2000",
    "2300-2304",
    "2400",
    "3000",
    "4000",
    "47624",
    "5000",
    "7000",
    "7777",
    "8000",
    "8080",
    "9000",
    "10000-10001",
    "10262",
    "11000",
    "12000",
    "20000",
    "21000",
    "28000"
)

$programs = @($exePath)
if (Test-Path -LiteralPath $launcherPath) {
    $programs += $launcherPath
}

$rules = New-Object System.Collections.Generic.List[hashtable]
$privatePeerRanges = @("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
$radminPeerRange = "26.0.0.0/8"

$profiles = Get-NetFirewallProfile
$disabledProfiles = @($profiles | Where-Object { -not $_.Enabled })
if ($disabledProfiles.Count -gt 0) {
    $disabledNames = ($disabledProfiles | ForEach-Object { $_.Name }) -join ", "
    if ($EnableFirewallProfiles) {
        Set-NetFirewallProfile -Profile Domain,Private,Public -Enabled True
        Write-Host "Enabled Windows Firewall profiles: Domain, Private, Public" -ForegroundColor Green
    } else {
        Write-Host "Windows Firewall disabled profiles: $disabledNames" -ForegroundColor Yellow
        if ($RadminOnly) {
            Write-Host "WARNING: -RadminOnly block rules do not work while Windows Firewall is disabled. Re-run with -EnableFirewallProfiles or enable Windows Firewall manually." -ForegroundColor Yellow
        }
    }
}

foreach ($program in $programs) {
    $name = [IO.Path]::GetFileNameWithoutExtension($program)
    $rules.Add(@{
        DisplayName = "RhakMu $name Inbound Program"
        Direction = "Inbound"
        Program = $program
        Action = "Allow"
        Profile = "Any"
    })
    $rules.Add(@{
        DisplayName = "RhakMu $name Outbound Program"
        Direction = "Outbound"
        Program = $program
        Action = "Allow"
        Profile = "Any"
    })
    foreach ($protocol in @("TCP", "UDP")) {
        $rules.Add(@{
            DisplayName = "RhakMu $name Inbound $protocol Ports"
            Direction = "Inbound"
            Program = $program
            Protocol = $protocol
            LocalPort = $ports
            RemoteAddress = $RemoteAddress
            Action = "Allow"
            Profile = "Any"
            EdgeTraversalPolicy = "Allow"
        })
        $rules.Add(@{
            DisplayName = "RhakMu $name Outbound $protocol Ports"
            Direction = "Outbound"
            Program = $program
            Protocol = $protocol
            RemotePort = $ports
            RemoteAddress = $RemoteAddress
            Action = "Allow"
            Profile = "Any"
        })
    }

    if ($RadminOnly) {
        $rules.Add(@{
            DisplayName = "RhakMu $name RadminOnly Allow UDP11223 Inbound"
            Direction = "Inbound"
            Program = $program
            Protocol = "UDP"
            LocalPort = "11223"
            RemoteAddress = $radminPeerRange
            Action = "Allow"
            Profile = "Any"
            EdgeTraversalPolicy = "Allow"
        })
        $rules.Add(@{
            DisplayName = "RhakMu $name RadminOnly Allow UDP11223 Outbound"
            Direction = "Outbound"
            Program = $program
            Protocol = "UDP"
            RemotePort = "11223"
            RemoteAddress = $radminPeerRange
            Action = "Allow"
            Profile = "Any"
        })
        $rules.Add(@{
            DisplayName = "RhakMu $name RadminOnly Block Private UDP11223 Inbound"
            Direction = "Inbound"
            Program = $program
            Protocol = "UDP"
            LocalPort = "11223"
            RemoteAddress = $privatePeerRanges
            Action = "Block"
            Profile = "Any"
        })
        $rules.Add(@{
            DisplayName = "RhakMu $name RadminOnly Block Private UDP11223 Outbound"
            Direction = "Outbound"
            Program = $program
            Protocol = "UDP"
            RemotePort = "11223"
            RemoteAddress = $privatePeerRanges
            Action = "Block"
            Profile = "Any"
        })
    }
}

$rules.Add(@{
    DisplayName = "RhakMu Multiplayer Inbound TCP Ports"
    Direction = "Inbound"
    Protocol = "TCP"
    LocalPort = $ports
    RemoteAddress = $RemoteAddress
    Action = "Allow"
    Profile = "Any"
    EdgeTraversalPolicy = "Allow"
})
$rules.Add(@{
    DisplayName = "RhakMu Multiplayer Inbound UDP Ports"
    Direction = "Inbound"
    Protocol = "UDP"
    LocalPort = $ports
    RemoteAddress = $RemoteAddress
    Action = "Allow"
    Profile = "Any"
    EdgeTraversalPolicy = "Allow"
})
$rules.Add(@{
    DisplayName = "RhakMu Multiplayer Outbound TCP Ports"
    Direction = "Outbound"
    Protocol = "TCP"
    RemotePort = $ports
    RemoteAddress = $RemoteAddress
    Action = "Allow"
    Profile = "Any"
})
$rules.Add(@{
    DisplayName = "RhakMu Multiplayer Outbound UDP Ports"
    Direction = "Outbound"
    Protocol = "UDP"
    RemotePort = $ports
    RemoteAddress = $RemoteAddress
    Action = "Allow"
    Profile = "Any"
})

$legacyRuleNames = @(
    "RhakMu Client Inbound Program",
    "RhakMu Multiplayer TCP Ports",
    "RhakMu Multiplayer UDP Ports"
)
foreach ($name in $legacyRuleNames) {
    $existing = Get-NetFirewallRule -DisplayName $name -ErrorAction SilentlyContinue
    if ($existing) {
        $existing | Remove-NetFirewallRule
        Write-Host "Removed legacy firewall rule: $name"
    }
}

Get-NetFirewallRule -DisplayName "RhakMu * RadminOnly * UDP11223 *" -ErrorAction SilentlyContinue | Remove-NetFirewallRule

foreach ($rule in $rules) {
    $existing = Get-NetFirewallRule -DisplayName $rule.DisplayName -ErrorAction SilentlyContinue
    if ($existing) {
        $existing | Remove-NetFirewallRule
    }

    New-NetFirewallRule @rule | Out-Null
    Write-Host "Installed firewall rule: $($rule.DisplayName)"
}

if ($RadminOnly) {
    Write-Host "RadminOnly mode enabled: RhakMu UDP 11223 is allowed for 26.0.0.0/8 and blocked for private LAN ranges." -ForegroundColor Green
}

Write-Host "Done. Run this on every PC that can host or join a RhakMu match."
