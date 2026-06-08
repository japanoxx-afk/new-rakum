param(
    [string]$GameDir = "C:\Program Files (x86)\TriggerSoft\RhakMu",
    [switch]$Restore   # put DWM8And16BitMitigation back (game needs it to launch)
)

# RhakMu uses DDrawCompat (ddraw.dll wrapper) for DirectDraw on modern Windows.
# DDrawCompat MUST NOT be combined with the Windows "DWM8And16BitMitigation" /
# "16BITCOLOR" / "256COLOR" compatibility shims (apphelp.dll) -- they both hook
# DirectDraw and the double-wrap crashes on DDraw re-init / 16-bit blits
# (iCARUS_InitDDraw ACCESS_VIOLATION in apphelp.dll, iCARUS16_Put16Image crash
# in the post-game screen). This removes those conflicting shims so DDrawCompat
# alone handles DirectDraw.

$ErrorActionPreference = "Stop"

function Test-IsAdmin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    (New-Object Security.Principal.WindowsPrincipal($id)).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)
}

$targets = @(
    (Join-Path $GameDir "Rhakmu.exe"),
    (Join-Path $GameDir "Launcher.exe")
)
$badFlags = @("DWM8And16BitMitigation", "16BITCOLOR", "256COLOR", "8And16BitTimedPriSync")

$keys = @(
    "HKCU:\Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers"
)
if (Test-IsAdmin) {
    $keys += "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers"
} else {
    Write-Host "Not elevated: only the HKCU (current user) shim will be cleaned. Re-run as Administrator to also clean HKLM." -ForegroundColor Yellow
}

if ($Restore) {
    foreach ($key in $keys) {
        if (-not (Test-Path $key)) { New-Item -Path $key -Force | Out-Null }
        $exe = Join-Path $GameDir "Rhakmu.exe"
        Set-ItemProperty -Path $key -Name $exe -Value "DWM8And16BitMitigation"
        Write-Host "Restored shim DWM8And16BitMitigation for $exe  ($key)" -ForegroundColor Green
    }
    Write-Host "Restart the game." -ForegroundColor Cyan
    return
}

foreach ($key in $keys) {
    if (-not (Test-Path $key)) { continue }
    $props = Get-ItemProperty $key
    foreach ($exe in $targets) {
        $val = $props.PSObject.Properties | Where-Object { $_.Name -eq $exe }
        if (-not $val) { continue }
        $tokens = ($val.Value -split '\s+') | Where-Object { $_ -ne '' }
        $kept = $tokens | Where-Object { $badFlags -notcontains $_ }
        # drop a lone leading "~" or "$" marker if nothing else remains
        $meaningful = $kept | Where-Object { $_ -ne '~' -and $_ -ne '$' }
        if (-not $meaningful) {
            Remove-ItemProperty -Path $key -Name $exe -ErrorAction SilentlyContinue
            Write-Host "Removed all compat flags for: $exe  ($key)" -ForegroundColor Green
        } elseif ((($kept -join ' ')) -ne $val.Value) {
            Set-ItemProperty -Path $key -Name $exe -Value ($kept -join ' ')
            Write-Host "Cleaned compat flags for $exe -> '$($kept -join ' ')'  ($key)" -ForegroundColor Green
        } else {
            Write-Host "No conflicting flags on $exe  ($key)" -ForegroundColor DarkGray
        }
    }
}

Write-Host ""
Write-Host "Done. DDrawCompat (ddraw.dll) will now handle DirectDraw without the Windows 16-bit shim." -ForegroundColor Cyan
Write-Host "Restart the game (and Explorer is not required)." -ForegroundColor Cyan
