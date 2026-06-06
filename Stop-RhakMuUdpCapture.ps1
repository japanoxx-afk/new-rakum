param(
    [string]$OutputDir = ".\rhakmu_packet_captures",
    [string]$LogsRoot = ".\logs",
    [switch]$NoGitUpload
)

$ErrorActionPreference = "Stop"

function Test-IsAdministrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function ConvertTo-SafeName([string]$Text) {
    if ([string]::IsNullOrWhiteSpace($Text)) { return "unknown" }
    return (($Text.Trim() -replace '[\\/:*?"<>|,=\s]+', "_") -replace "_+", "_").Trim("_")
}

function Get-GitExe {
    $cmd = Get-Command git -ErrorAction SilentlyContinue
    if ($null -ne $cmd) { return $cmd.Source }

    $candidates = @(
        "$env:LOCALAPPDATA\GitHubDesktop\app-3.5.12\resources\app\git\cmd\git.exe",
        "$env:ProgramFiles\Git\cmd\git.exe",
        "${env:ProgramFiles(x86)}\Git\cmd\git.exe"
    )

    foreach ($candidate in $candidates) {
        if (-not [string]::IsNullOrWhiteSpace($candidate) -and (Test-Path -LiteralPath $candidate)) {
            return $candidate
        }
    }

    return $null
}

function Copy-IfExists([string]$Source, [string]$Destination) {
    if (Test-Path -LiteralPath $Source) {
        Copy-Item -LiteralPath $Source -Destination $Destination -Force
        return $true
    }
    return $false
}

function Invoke-GitChecked(
    [string]$GitExe,
    [string[]]$Arguments,
    [switch]$AllowFailure
) {
    & $GitExe @Arguments
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0 -and -not $AllowFailure) {
        throw "git $($Arguments -join ' ') failed with exit code $exitCode"
    }
    return $exitCode
}

if (-not (Test-IsAdministrator)) {
    throw "Run this script from an elevated PowerShell window. pktmon packet capture requires administrator rights."
}

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $root

$fullOutputDir = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($OutputDir)
$statePath = Join-Path $fullOutputDir "active_capture.txt"
$stateJsonPath = Join-Path $fullOutputDir "active_capture.json"

if (-not (Test-Path -LiteralPath $statePath)) {
    throw "No active capture state found: $statePath"
}

$etlPath = (Get-Content -LiteralPath $statePath -Raw).Trim()
if ([string]::IsNullOrWhiteSpace($etlPath)) {
    throw "Active capture state is empty: $statePath"
}

$captureState = $null
if (Test-Path -LiteralPath $stateJsonPath) {
    try {
        $captureState = Get-Content -LiteralPath $stateJsonPath -Raw | ConvertFrom-Json
    } catch {
        Write-Host "Capture state JSON could not be read: $($_.Exception.Message)" -ForegroundColor Yellow
    }
}

pktmon stop | Out-Null

$pcapPath = [IO.Path]::ChangeExtension($etlPath, ".pcapng")
$txtPath = [IO.Path]::ChangeExtension($etlPath, ".txt")

pktmon etl2pcap $etlPath --out $pcapPath | Out-Null
pktmon etl2txt $etlPath --out $txtPath | Out-Null

Remove-Item -LiteralPath $statePath -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $stateJsonPath -Force -ErrorAction SilentlyContinue

$localIp = if ($null -ne $captureState -and -not [string]::IsNullOrWhiteSpace($captureState.LocalIp)) { $captureState.LocalIp } else { "unknown-ip" }
$safeIp = if ($null -ne $captureState -and -not [string]::IsNullOrWhiteSpace($captureState.SafeIp)) { $captureState.SafeIp } else { ConvertTo-SafeName $localIp }
$baseName = if ($null -ne $captureState -and -not [string]::IsNullOrWhiteSpace($captureState.BaseName)) { $captureState.BaseName } else { [IO.Path]::GetFileNameWithoutExtension($etlPath) }
$resolvedLogsRoot = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($LogsRoot)
$sessionDir = Join-Path (Join-Path $resolvedLogsRoot $safeIp) $baseName
New-Item -ItemType Directory -Force -Path $sessionDir | Out-Null

$copied = New-Object System.Collections.Generic.List[string]
foreach ($path in @($etlPath, $pcapPath, $txtPath)) {
    if (Copy-IfExists $path (Join-Path $sessionDir ([IO.Path]::GetFileName($path)))) {
        $copied.Add((Join-Path $sessionDir ([IO.Path]::GetFileName($path))))
    }
}
if ($null -ne $captureState -and -not [string]::IsNullOrWhiteSpace($captureState.MetaPath)) {
    $metaSource = [string]$captureState.MetaPath
    if (Copy-IfExists $metaSource (Join-Path $sessionDir ([IO.Path]::GetFileName($metaSource)))) {
        $copied.Add((Join-Path $sessionDir ([IO.Path]::GetFileName($metaSource))))
    }
}

$dummyLogs = @(
    @{ Source = ".\rhakmu_dummy_server_events.log"; Name = "${baseName}_dummy_server_events.txt" },
    @{ Source = ".\rhakmu_dummy_server_terminal.log"; Name = "${baseName}_dummy_server_terminal.txt" },
    @{ Source = ".\rhakmu_dummy_server_stdout.log"; Name = "${baseName}_dummy_server_stdout.txt" },
    @{ Source = ".\rhakmu_dummy_server_stderr.log"; Name = "${baseName}_dummy_server_stderr.txt" }
)

foreach ($log in $dummyLogs) {
    $sourcePath = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($log.Source)
    $destinationPath = Join-Path $sessionDir $log.Name
    if (Copy-IfExists $sourcePath $destinationPath) {
        $copied.Add($destinationPath)
    }
}

$summaryPath = Join-Path $sessionDir "${baseName}_summary.txt"
@(
    "Stopped: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss.fff')",
    "Computer: $env:COMPUTERNAME",
    "LocalIp: $localIp",
    "Port: $(if ($null -ne $captureState) { $captureState.Port } else { '' })",
    "ETL: $etlPath",
    "PCAP: $pcapPath",
    "TEXT: $txtPath",
    "SessionDir: $sessionDir",
    "CopiedFiles:",
    ($copied | ForEach-Object { "  $_" })
) | Set-Content -LiteralPath $summaryPath -Encoding UTF8
$copied.Add($summaryPath)

$gitUploaded = $false
if (-not $NoGitUpload) {
    $gitExe = Get-GitExe
    $gitDir = Join-Path $root ".git"
    if ([string]::IsNullOrWhiteSpace($gitExe)) {
        Write-Host "Git executable was not found. Files were saved locally only." -ForegroundColor Yellow
    } elseif (-not (Test-Path -LiteralPath $gitDir)) {
        Write-Host "This folder is not a git repository. Files were saved locally only: $sessionDir" -ForegroundColor Yellow
    } else {
        try {
            [void](Invoke-GitChecked $gitExe @("add", "--", $sessionDir))
        } catch {
            Write-Host "Git add failed. Files were saved locally only: $($_.Exception.Message)" -ForegroundColor Yellow
        }

        $status = & $gitExe status --short -- $sessionDir
        if (-not [string]::IsNullOrWhiteSpace(($status -join ""))) {
            try {
                $message = "Add RhakMu capture logs for $localIp"
                [void](Invoke-GitChecked $gitExe @("commit", "-m", $message))
                [void](Invoke-GitChecked $gitExe @("pull", "--rebase", "origin", "main"))
                [void](Invoke-GitChecked $gitExe @("push", "origin", "main"))
                $gitUploaded = $true
            } catch {
                Write-Host "Git upload failed after saving files locally: $($_.Exception.Message)" -ForegroundColor Yellow
                Write-Host "Manual recovery command:" -ForegroundColor Yellow
                Write-Host "  git pull --rebase origin main; git push origin main" -ForegroundColor Yellow
            }
        } else {
            try {
                [void](Invoke-GitChecked $gitExe @("pull", "--rebase", "origin", "main"))
                [void](Invoke-GitChecked $gitExe @("push", "origin", "main"))
                $gitUploaded = $true
            } catch {
                Write-Host "No new capture log changes to commit, and push/pull recovery did not complete: $($_.Exception.Message)" -ForegroundColor Yellow
            }
        }
    }
}

Write-Host "RhakMu UDP capture stopped." -ForegroundColor Green
Write-Host "LocalIp: $localIp"
Write-Host "ETL:   $etlPath"
Write-Host "PCAP:  $pcapPath"
Write-Host "TEXT:  $txtPath"
Write-Host "Saved for analysis: $sessionDir"
Write-Host ""
if ($gitUploaded) {
    Write-Host "Capture files and dummy server logs were uploaded to GitHub." -ForegroundColor Green
} else {
    Write-Host "Send or upload the files from the analysis folder above." -ForegroundColor Yellow
}
