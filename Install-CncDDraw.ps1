param(
    [string]$GameDir  = "C:\Program Files (x86)\TriggerSoft\RhakMu",
    [string]$SrcDir   = "C:\Users\seo\Downloads\cnc-ddraw"
)

# Installs cnc-ddraw DirectDraw wrapper into the RhakMu game directory.
# Replaces the system DDRAW.dll dispatch with a Direct3D9 back-end,
# preventing the SysWOW64\DDRAW.dll+0x000149de access-violation crash
# that occurs during the menu-to-battle transition on test2.
#
# The game directory takes precedence over SysWOW64 for DLL lookup,
# so placing ddraw.dll here intercepts all DirectDraw calls without
# modifying the system DLL.

$ErrorActionPreference = "Stop"

if (-not (Test-Path $SrcDir)) { throw "cnc-ddraw source not found: $SrcDir" }

$dllSrc = Join-Path $SrcDir "ddraw.dll"
$iniSrc = Join-Path $SrcDir "ddraw.ini"

if (-not (Test-Path $dllSrc)) { throw "ddraw.dll not found in: $SrcDir" }
if (-not (Test-Path $GameDir)) { throw "Game directory not found: $GameDir" }

$dllDst = Join-Path $GameDir "ddraw.dll"
$iniDst = Join-Path $GameDir "ddraw.ini"

# Back up existing ddraw.dll if present (unlikely in game dir, but safe)
if (Test-Path $dllDst) {
    $bak = "$dllDst.bak_$(Get-Date -Format yyyyMMdd_HHmmss)"
    Copy-Item $dllDst $bak
    Write-Host "Backed up existing ddraw.dll -> $bak" -ForegroundColor Yellow
}

Copy-Item $dllSrc $dllDst -Force
Write-Host "Installed: ddraw.dll  ($([Math]::Round((Get-Item $dllDst).Length/1KB)) KB)" -ForegroundColor Green

if (Test-Path $iniSrc) {
    Copy-Item $iniSrc $iniDst -Force
    Write-Host "Installed: ddraw.ini" -ForegroundColor Green
}

# Patch ini: enable windowed-fullscreen (borderless) for compatibility
# and force direct3d9 renderer (most stable on Windows 11 with NVIDIA)
if (Test-Path $iniDst) {
    $ini = [IO.File]::ReadAllText($iniDst)
    # renderer=auto  ->  renderer=direct3d9
    $ini = $ini -replace '(?m)^renderer=.*$', 'renderer=direct3d9'
    # fullscreen=false -> fullscreen=true  (game expects exclusive fullscreen)
    $ini = $ini -replace '(?m)^fullscreen=.*$', 'fullscreen=true'
    [IO.File]::WriteAllText($iniDst, $ini, [Text.Encoding]::UTF8)
    Write-Host "Configured: renderer=direct3d9, fullscreen=true" -ForegroundColor Cyan
}

Write-Host ""
Write-Host "cnc-ddraw installed to $GameDir" -ForegroundColor Green
Write-Host "SysWOW64\DDRAW.dll crash should no longer occur." -ForegroundColor Cyan
Write-Host "Run Apply-RhakMuStable.ps1 first if not already patched, then start the game." -ForegroundColor Cyan
