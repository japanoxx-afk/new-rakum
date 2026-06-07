param(
    [int]$Port = 11223
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path

# Kill any existing server listening on port 11223
$existing = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($existing) {
    $pids = $existing | Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($pid in $pids) {
        $proc = Get-Process -Id $pid -ErrorAction SilentlyContinue
        if ($proc) {
            Write-Host "Stopping existing process: $($proc.Name) (pid=$pid)" -ForegroundColor Yellow
            Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
            Start-Sleep -Milliseconds 500
        }
    }
}

$serverScript = Join-Path $root "server.py"
if (-not (Test-Path $serverScript)) {
    Write-Error "server.py not found: $serverScript"
    exit 1
}

# Find Python
$python = $null
$candidates = @(
    "C:\Users\seo\AppData\Local\Programs\Python\Python314\python.exe",
    "C:\Users\seo\AppData\Local\Programs\Python\Python313\python.exe",
    "C:\Users\seo\AppData\Local\Programs\Python\Python312\python.exe",
    "python"
)
foreach ($c in $candidates) {
    if (Get-Command $c -ErrorAction SilentlyContinue) {
        $python = $c; break
    }
    if (Test-Path $c) {
        $python = $c; break
    }
}
if (-not $python) {
    Write-Error "Python not found. Install Python 3.8+ and try again."
    exit 1
}

Write-Host "RhakMu Private Server" -ForegroundColor Green
Write-Host "Port  : $Port" -ForegroundColor Cyan
Write-Host "Python: $python" -ForegroundColor Cyan
Write-Host "Press Ctrl+C to stop."
Write-Host ""

& $python $serverScript
