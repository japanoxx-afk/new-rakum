param(
    [string]$GameDir = "C:\Program Files (x86)\TriggerSoft\RhakMu",
    [string]$RemoteAddress = "Any"
)

$ErrorActionPreference = "Stop"

$exePath = Join-Path $GameDir "Rhakmu.exe"
if (-not (Test-Path -LiteralPath $exePath)) {
    throw "Rhakmu.exe not found: $exePath"
}

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

$rules = @(
    @{
        DisplayName = "RhakMu Client Inbound Program"
        Direction = "Inbound"
        Program = $exePath
        Action = "Allow"
        Profile = "Any"
    },
    @{
        DisplayName = "RhakMu Multiplayer TCP Ports"
        Direction = "Inbound"
        Protocol = "TCP"
        LocalPort = $ports
        RemoteAddress = $RemoteAddress
        Action = "Allow"
        Profile = "Any"
    },
    @{
        DisplayName = "RhakMu Multiplayer UDP Ports"
        Direction = "Inbound"
        Protocol = "UDP"
        LocalPort = $ports
        RemoteAddress = $RemoteAddress
        Action = "Allow"
        Profile = "Any"
    }
)

foreach ($rule in $rules) {
    $existing = Get-NetFirewallRule -DisplayName $rule.DisplayName -ErrorAction SilentlyContinue
    if ($existing) {
        $existing | Remove-NetFirewallRule
    }

    New-NetFirewallRule @rule | Out-Null
    Write-Host "Installed firewall rule: $($rule.DisplayName)"
}

Write-Host "Done. Run this on every PC that can host or join a RhakMu match."
