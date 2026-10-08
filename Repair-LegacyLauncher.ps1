param(
    [Parameter(Mandatory=$true)][string]$OldExe,
    [Parameter(Mandatory=$true)][string]$Replacement,
    [Parameter(Mandatory=$true)][string]$ExpectedSha256,
    [int]$WaitSeconds = 900
)
# One-time recovery for installed launchers whose embedded updater deletes/moves
# their own running executable. Never terminate the launcher or its server.
$ErrorActionPreference = 'Stop'
$old = (Resolve-Path -LiteralPath $OldExe).Path
$source = (Resolve-Path -LiteralPath $Replacement).Path
if ($old -eq $source) { throw 'Source and destination must differ.' }
if ([IO.Path]::GetFileName($old) -notmatch '^RhakMuLauncher.*\.exe$') { throw 'Unexpected target filename.' }
if ((Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash -ne $ExpectedSha256) { throw 'Replacement hash mismatch.' }
$log = $old + '.repair.log'
$backup = $old + '.backup-' + [guid]::NewGuid().ToString('N')
$staged = $old + '.repair-' + [guid]::NewGuid().ToString('N')
$deadline = (Get-Date).AddSeconds($WaitSeconds)
'Waiting for the old launcher and its server to close normally.' | Set-Content -LiteralPath $log
try {
    Copy-Item -LiteralPath $source -Destination $staged
    while ($true) {
        if ((Get-Date) -ge $deadline) { throw 'Timed out. Close the old launcher/server and rerun repair.' }
        $running = @(Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -and $_.ExecutablePath -eq $old })
        if ($running.Count) { Start-Sleep -Seconds 2; continue }
        try {
            # Atomic replacement with a recoverable copy of the old executable.
            [IO.File]::Replace($staged, $old, $backup)
            break
        } catch [IO.IOException] { Start-Sleep -Seconds 2 }
    }
    if ((Get-FileHash -LiteralPath $old -Algorithm SHA256).Hash -ne $ExpectedSha256) { throw 'Installed hash verification failed.' }
    "SUCCESS: v0.9012 installed at $old`r`nOriginal backup: $backup" | Set-Content -LiteralPath $log
} catch {
    ('ERROR: ' + $_.Exception.Message) | Add-Content -LiteralPath $log
    throw
} finally {
    if (Test-Path -LiteralPath $staged) { Remove-Item -LiteralPath $staged }
}
