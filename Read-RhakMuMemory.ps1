# Read-RhakMuMemory.ps1
# Reads key memory addresses from the running Rhakmu.exe process.
# No ASLR = addresses are fixed. Run as Administrator while game is running.
# Usage: powershell -ExecutionPolicy Bypass -File Read-RhakMuMemory.ps1 [-Watch]
#   -Watch : refresh every 2 seconds until Ctrl+C

param([switch]$Watch, [string]$OutFile = "")

$ErrorActionPreference = "Stop"

$sig = @"
using System;
using System.Runtime.InteropServices;
public class Mem {
    [DllImport("kernel32.dll")] public static extern IntPtr OpenProcess(int a, bool b, int c);
    [DllImport("kernel32.dll")] public static extern bool ReadProcessMemory(IntPtr h, IntPtr a, byte[] buf, int n, out int read);
    [DllImport("kernel32.dll")] public static extern bool CloseHandle(IntPtr h);
}
"@
Add-Type -TypeDefinition $sig -Language CSharp

function Read-Bytes($hProc, [int]$va, [int]$n) {
    $buf = New-Object byte[] $n
    $read = 0
    [Mem]::ReadProcessMemory($hProc, [IntPtr]$va, $buf, $n, [ref]$read) | Out-Null
    return $buf
}
function Read-U8($h,$va)  { (Read-Bytes $h $va 1)[0] }
function Read-U32($h,$va) { [BitConverter]::ToUInt32((Read-Bytes $h $va 4), 0) }

$logLines = [System.Collections.Generic.List[string]]::new()
function Log($msg, $color = "White") {
    Write-Host $msg -ForegroundColor $color
    $logLines.Add($msg)
}
function Flush {
    if ($OutFile) { $logLines | Out-File -FilePath $OutFile -Encoding utf8 -Append }
}

$proc = Get-Process -Name "Rhakmu" -ErrorAction SilentlyContinue
if (-not $proc) { Write-Host "Rhakmu.exe not running." -ForegroundColor Red; exit 1 }

$PROCESS_VM_READ = 0x0010
$hProc = [Mem]::OpenProcess($PROCESS_VM_READ, $false, $proc.Id)
if ($hProc -eq [IntPtr]::Zero) { throw "OpenProcess failed (run as Administrator?)" }

function Show-State {
    # --- core flags ---
    $connMgr   = Read-U8  $hProc 0x6E0980  # connected flag (1=OK)
    $roomNetMgr= Read-U32 $hProc 0x7F668C  # RoomNetMGR pointer (0=uninit)
    $battleSt  = Read-U32 $hProc 0x6DFC74  # battle state (5=running)
    $mySlot    = Read-U8  $hProc 0x6E5382  # slot (0=host,1=guest)
    $netMode   = Read-U32 $hProc 0x6E0576  # network mode (3=P2P)
    $seed      = Read-U32 $hProc 0x6E0970  # random seed
    $gameType  = Read-U32 $hProc 0x6DFCC6  # game-type word (6=required for countdown)

    # --- RoomNetMGR send buffer (this+4) ---
    $rnSendBuf = 0
    if ($roomNetMgr -ne 0) {
        $rnSendBuf = Read-U32 $hProc ($roomNetMgr + 4)
    }

    # --- b401xx area (slot tracking) ---
    $b401b4 = Read-U8 $hProc 0xb401b4
    $b401bc = Read-U8 $hProc 0xb401bc

    $ts = Get-Date -Format "HH:mm:ss"
    Log ""
    Log "[$ts] ===== Rhakmu.exe Memory Snapshot =====" Cyan

    $cm = if($connMgr -eq 1){"OK 1 (CONNECTED)"}elseif($connMgr -eq 0){"NG 0 (NOT connected)"}else{"? $connMgr"}
    Log "  [0x6E0980] ConnMgr connected flag : $cm"

    $rn = if($roomNetMgr -ne 0){"OK 0x$("{0:X8}" -f $roomNetMgr)"}else{"NG NULL (uninit)"}
    Log "  [0x7F668C] RoomNetMGR ptr         : $rn"

    if ($roomNetMgr -ne 0) {
        $sb = if($rnSendBuf -ne 0){"OK 0x$("{0:X8}" -f $rnSendBuf)"}else{"NG NULL (can't send RMPK)"}
        Log "  [RoomNetMGR+4] send buffer      : $sb"
    }

    $bs = if($battleSt -eq 5){"OK 5 (BATTLE RUNNING)"}elseif($battleSt -eq 0){"NG 0 (lobby)"}else{"NG $battleSt"}
    Log "  [0x6DFC74] battle state            : $bs"

    $sl = if($mySlot -eq 0){"HOST (0)"}elseif($mySlot -eq 1){"GUEST (1)"}else{"? $mySlot"}
    Log "  [0x6E5382] my slot                 : $sl"

    Log "  [0x6E0576] network mode            : $netMode  (3=P2P expected)"
    Log "  [0x6DFCC6] game-type word          : $gameType  (6=required for countdown)"
    Log "  [0x6E0970] random seed             : 0x$("{0:X8}" -f $seed)"
    Log "  [0xB401B4] peer slot byte          : $b401b4"
    Log "  [0xB401BC] local slot byte         : $b401bc"

    Log ""
    Log "  -- DIAGNOSIS --" Yellow
    if ($roomNetMgr -eq 0) {
        Log "  NG RoomNetMGR not initialized -> patch not firing" Red
    } elseif ($rnSendBuf -eq 0) {
        Log "  NG RoomNetMGR send buffer null -> RMPKSend will skip all sends" Red
    } elseif ($connMgr -eq 0) {
        Log "  NG Connection manager not connected -> RMPKSend_GameStart will abort" Red
        Log "     P2P handshake incomplete: host cannot send 0x100A until connected=1" Red
    } elseif ($battleSt -ne 5) {
        Log "  NG battle state != 5 -> turn engine not started" Red
    } else {
        Log "  OK All flags look good -- lockstep should be running" Green
    }
    Flush
}

if ($OutFile) {
    "# RhakMu Memory Log - $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" | Out-File -FilePath $OutFile -Encoding utf8
    Write-Host "Saving output to: $OutFile" -ForegroundColor DarkCyan
}

if ($Watch) {
    Write-Host "Watch mode - refreshing every 2s. Press Ctrl+C to stop." -ForegroundColor DarkCyan
    try {
        while ($true) {
            Show-State
            Start-Sleep -Seconds 2
        }
    } finally {
        [Mem]::CloseHandle($hProc) | Out-Null
    }
} else {
    Show-State
    [Mem]::CloseHandle($hProc) | Out-Null
}
