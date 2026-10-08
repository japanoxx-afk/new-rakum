# Isolated mocks: no real adapters are changed.
$testDir = Join-Path ([IO.Path]::GetTempPath()) ('rhakmu-test-' + [guid]::NewGuid())
New-Item -ItemType Directory -Path $testDir | Out-Null
$global:rhakmuMocks = @(
    [pscustomobject]@{Name='Radmin';InterfaceDescription='Radmin';Status='Up';InterfaceGuid='rad'},
    [pscustomobject]@{Name='Hamachi';InterfaceDescription='Hamachi';Status='Up';InterfaceGuid='ham'},
    [pscustomobject]@{Name='Hamachi off';InterfaceDescription='Hamachi';Status='Disabled';InterfaceGuid='off'})
$global:rhakmuPolls=0
$global:rhakmuDisabled=0
$global:rhakmuEnabled=0
function Get-NetAdapter { $global:rhakmuMocks }
function Get-NetIPAddress { param($AddressFamily,[Parameter(ValueFromPipeline)]$InputObject) process { [pscustomobject]@{IPAddress='26.1.2.3'} } }
function Disable-NetAdapter { param([Parameter(ValueFromPipeline)]$InputObject,[switch]$Confirm) process { $InputObject.Status='Disabled';$global:rhakmuDisabled++ } }
function Enable-NetAdapter { param([Parameter(ValueFromPipeline)]$InputObject,[switch]$Confirm) process { $InputObject.Status='Up';$global:rhakmuEnabled++ } }
function Get-Process { param($Name,$ErrorAction) $global:rhakmuPolls++;if($global:rhakmuPolls -eq 2){[pscustomobject]@{Id=123}} }
function Start-Process { param($FilePath,$WorkingDirectory,[switch]$PassThru,$WindowStyle) [pscustomobject]@{HasExited=$true} }
function Start-Sleep { param($Seconds) }
# Use an existing file only to satisfy the game's presence check.
$gameDir = Join-Path $testDir 'game'
New-Item -ItemType Directory -Path $gameDir | Out-Null
New-Item -ItemType File -Path (Join-Path $gameDir 'Launcher.exe') | Out-Null
& (Join-Path $PSScriptRoot 'radmin_session.ps1') -StateDir $testDir -GameDir $gameDir
$result = Get-Content (Join-Path $testDir 'status.txt')
if ($result -ne 'RESTORED' -or $global:rhakmuDisabled -ne 1 -or $global:rhakmuEnabled -ne 1 -or $global:rhakmuMocks[2].Status -ne 'Disabled') { throw "Lifecycle failed: $result" }
if (Test-Path (Join-Path $testDir 'adapters.json')) { throw 'State not cleared' }
Write-Output 'PASS: game lifecycle restores only originally enabled Hamachi.'
