param([string]$GameDir, [Parameter(Mandatory=$true)][string]$StateDir, [switch]$Restore)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'radmin_address.ps1')
$state = Join-Path $StateDir 'adapters.json'
$status = Join-Path $StateDir 'status.txt'
$mutex = [Threading.Mutex]::new($false, 'Local\RhakMuRadminSession')
$locked = $false
$changed = $false
function Report($s) { $s | Set-Content -LiteralPath $status -Encoding UTF8 }
function RestoreAdapters {
    Restore-RadminAddress $StateDir
    if (Test-Path -LiteralPath $state) {
        $saved = @(Get-Content -LiteralPath $state -Raw | ConvertFrom-Json)
        foreach ($guid in $saved) {
            # Windows PowerShell 5 represents a JSON [] pipeline as a null item.
            # No Hamachi adapters were changed in that session: nothing to restore.
            if (-not "$guid") { continue }
            $a = Get-NetAdapter | Where-Object { "$($_.InterfaceGuid)" -eq "$guid" }
            if (-not $a) { throw "Saved adapter missing: $guid" }
            if ($a.Status -eq 'Disabled') { $a | Enable-NetAdapter -Confirm:$false }
        }
        Remove-Item -LiteralPath $state
    }
}
try {
    try { $locked = $mutex.WaitOne(0) } catch [Threading.AbandonedMutexException] { $locked = $true }
    if (-not $locked) { throw 'Another Radmin game session is active.' }
    if (Get-Process Rhakmu,Launcher -ErrorAction SilentlyContinue) { throw 'Close the game and game launcher first.' }
    if ($Restore) { RestoreAdapters; Report 'RESTORED'; exit 0 }
    if ((Test-Path -LiteralPath $state) -or (Test-Path -LiteralPath (Join-Path $StateDir 'address.json'))) {
        Report 'RECOVERING'
        RestoreAdapters
    }
    $rad = @(Get-NetAdapter | Where-Object { $_.Status -eq 'Up' -and ($_.Name -match 'Radmin' -or $_.InterfaceDescription -match 'Radmin|Famatech') })
    if (-not $rad -or -not ($rad | Get-NetIPAddress -AddressFamily IPv4 | Where-Object IPAddress -like '26.*')) { throw 'Connected Radmin adapter not found.' }
    $radIPs = @($rad | Get-NetIPAddress -AddressFamily IPv4 | Where-Object IPAddress -like '26.*' | Select-Object -ExpandProperty IPAddress -Unique)
    if ($radIPs.Count -ne 1) { throw 'Exactly one Radmin IPv4 address is required.' }
    $exe = Join-Path $GameDir 'Launcher.exe'
    if (-not (Test-Path -LiteralPath $exe)) { throw 'Game Launcher.exe not found.' }
    $ham = @(Get-NetAdapter | Where-Object { ($_.Name -match 'Hamachi' -or $_.InterfaceDescription -match 'Hamachi') -and $_.Status -ne 'Disabled' })
    ConvertTo-Json -InputObject @($ham | ForEach-Object { "$($_.InterfaceGuid)" }) | Set-Content -LiteralPath $state -Encoding UTF8
    $changed = $true
    Enable-RadminAddress $GameDir $StateDir $radIPs[0]
    foreach ($a in $ham) { $a | Disable-NetAdapter -Confirm:$false }
    if (Get-NetAdapter | Where-Object { ($_.Name -match 'Hamachi' -or $_.InterfaceDescription -match 'Hamachi') -and $_.Status -ne 'Disabled' }) { throw 'Hamachi disable verification failed.' }
    Report 'STARTING'
    $child = Start-Process -FilePath $exe -WorkingDirectory $GameDir -PassThru -WindowStyle Normal
    $deadline = (Get-Date).AddSeconds(120)
    $seenGame = $false
    $empty = 0
    do {
        Start-Sleep -Seconds 2
        $games = @(Get-Process Rhakmu -ErrorAction SilentlyContinue)
        if ($games.Count) { $seenGame = $true; $empty = 0; Report 'PLAYING' } else { $empty++ }
        # Keep the isolation in place if another program re-enables Hamachi.
        foreach ($a in @(Get-NetAdapter | Where-Object { ($_.Name -match 'Hamachi' -or $_.InterfaceDescription -match 'Hamachi') -and $_.Status -ne 'Disabled' })) {
            $saved = @(Get-Content -LiteralPath $state -Raw | ConvertFrom-Json)
            if ("$($a.InterfaceGuid)" -notin $saved) { throw 'A new Hamachi adapter appeared. Close the game and restore networking.' }
            $a | Disable-NetAdapter -Confirm:$false
        }
    } while (($seenGame -and $empty -lt 3) -or (-not $seenGame -and (-not $child.HasExited -or (Get-Date) -lt $deadline)))
    RestoreAdapters
    $changed = $false
    Report 'RESTORED'
} catch {
    Report ('ERROR: ' + $_.Exception.Message)
    exit 1
} finally {
    if ($changed) {
        try {
            if (Get-Process Rhakmu,Launcher -ErrorAction SilentlyContinue) { throw 'Game still running. Close it, then use Restore.' }
            RestoreAdapters
        } catch { Report ('RESTORE ERROR: ' + $_.Exception.Message) }
    }
    if ($locked) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}
