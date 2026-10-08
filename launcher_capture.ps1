param([Parameter(Mandatory=$true)][string]$OutputDir, [string]$ServerDir)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$owned = $false
$failed = $false
function Status($text) { $text | Set-Content -LiteralPath (Join-Path $OutputDir 'status.txt') -Encoding UTF8 }
function Pkt([string[]]$Arguments) {
    $result = & pktmon @Arguments 2>&1
    $code = $LASTEXITCODE
    $result | Out-File -LiteralPath (Join-Path $OutputDir 'capture.log') -Append -Encoding UTF8
    if ($code -ne 0) { throw "pktmon $($Arguments -join ' '): $result" }
}
try {
    # Do not clear another application's global packet filters.
    $filters = (& pktmon filter list 2>&1 | Out-String)
    $filterCode = $LASTEXITCODE
    $filters | Out-File -LiteralPath (Join-Path $OutputDir 'capture.log') -Encoding UTF8
    if ($filterCode -ne 0 -or $filters -notmatch '(?im)^\s*(\uC5C6\uC74C|None\.?|No filters\.?)\s*$') {
        throw 'Existing or unrecognized pktmon filters. Close other capture tools and check pktmon filter list first.'
    }
    Status 'Starting capture...'
    Pkt @('start','--capture','--comp','nics','--pkt-size','256','--file-size','128','--file-name',(Join-Path $OutputDir 'packets.etl'))
    $owned = $true
    $end = (Get-Date).AddSeconds(120)
    while ((Get-Date) -lt $end -and -not (Test-Path -LiteralPath (Join-Path $OutputDir 'stop'))) {
        Status ("CAPTURING: {0}s remaining" -f [int]($end - (Get-Date)).TotalSeconds)
        Start-Sleep -Seconds 1
    }
} catch {
    $failed = $true
    $_ | Out-File -LiteralPath (Join-Path $OutputDir 'error.txt') -Encoding UTF8
} finally {
    if ($owned) {
        Status 'Saving capture...'
        try { Pkt @('stop') } catch { $failed = $true; $_ | Out-File (Join-Path $OutputDir 'error.txt') -Append }
        foreach ($conversion in @('etl2pcap','etl2txt')) {
            $ext = if ($conversion -eq 'etl2pcap') { 'pcapng' } else { 'txt' }
            try { Pkt @($conversion,(Join-Path $OutputDir 'packets.etl'),'-o',(Join-Path $OutputDir "packets.$ext")) }
            catch { $failed = $true; $_ | Out-File (Join-Path $OutputDir 'error.txt') -Append }
        }
    }
    try {
        & { Get-NetIPAddress -AddressFamily IPv4 | Format-List; Get-NetIPInterface -AddressFamily IPv4 | Format-Table; route print -4; Get-NetUDPEndpoint | Format-Table; Get-NetFirewallProfile | Format-Table Name,Enabled,DefaultInboundAction } |
            Out-File -LiteralPath (Join-Path $OutputDir 'network.txt') -Encoding UTF8
        if (Test-Path -LiteralPath (Join-Path $ServerDir 'server.log')) {
            Get-Content -LiteralPath (Join-Path $ServerDir 'server.log') -Tail 3000 |
                Out-File -LiteralPath (Join-Path $OutputDir 'server.log') -Encoding UTF8
        }
    } catch { $failed = $true; $_ | Out-File (Join-Path $OutputDir 'error.txt') -Append }
    if ($failed) { Status 'ERROR: see error.txt'; exit 1 }
    Status 'DONE'
}
