#Requires -Version 5
<#
  라크무 반응속도 개선 패치 (클라이언트 1.000d 전용)

  사용법:
    1) 게임을 1.000d 까지 업데이트
    2) 게임을 완전히 종료
    3) 이 파일을 마우스 우클릭 -> "PowerShell로 실행" (관리자 권한 권장)

  하는 일:
    - 명령 지연(lockstep command latency)을 4 -> 1 턴으로 낮춰 클릭 반응을 빠르게 함.
    - Rhakmu.exe 의 단 1바이트만 변경. 백업 자동 생성.
    - 서버/다른 파일/통계화면(Quit) 경로는 건드리지 않음.

  되돌리기:  이 스크립트를  -Revert  옵션으로 실행
  멀티플레이: 같이 하는 모든 PC가 동일한 값이어야 함 (-Latency 값을 똑같이).
#>
param(
    [string]$ExePath = "C:\Program Files (x86)\TriggerSoft\RhakMu\Rhakmu.exe",
    [ValidateRange(1,4)][int]$Latency = 1,
    [switch]$Revert
)

$ErrorActionPreference = "Stop"

function Fail($msg) { Write-Host "[오류] $msg" -ForegroundColor Red; exit 1 }

if (-not (Test-Path -LiteralPath $ExePath)) {
    Fail "게임을 찾을 수 없습니다: $ExePath`n경로가 다르면 -ExePath 로 지정하세요."
}
if (Get-Process -Name "Rhakmu" -ErrorAction SilentlyContinue) {
    Fail "게임이 실행 중입니다. 게임을 완전히 종료한 뒤 다시 실행하세요."
}

$bytes = [IO.File]::ReadAllBytes($ExePath)

# 지연값 초기화 코드 3곳을 찾는다:  mov word [eax+0x48], <N> ; call ...
#   = 바이트 시그니처  66 C7 40 48 <N> 00 E8
# 주소 순서대로  Game_Single(1) / Game_Multi(4) / Game_Replay(4) 이고,
# 가운데(Game_Multi)가 실제 대전(컴퓨터전 포함)에서 쓰는 값이다.
$sites = @()
for ($i = 0; $i -lt $bytes.Length - 7; $i++) {
    if ($bytes[$i] -eq 0x66 -and $bytes[$i+1] -eq 0xC7 -and $bytes[$i+2] -eq 0x40 -and
        $bytes[$i+3] -eq 0x48 -and $bytes[$i+5] -eq 0x00 -and $bytes[$i+6] -eq 0xE8) {
        $sites += $i
    }
}
if ($sites.Count -ne 3) {
    Fail ("지연값 코드를 찾지 못했습니다 (발견 $($sites.Count)개, 기대 3개).`n" +
          "이 패치는 클라이언트 1.000d 전용입니다. 먼저 1.000d 까지 업데이트하세요.")
}
$sites  = $sites | Sort-Object
$multi  = $sites[1]          # 가운데 = Game_Multi
$immOff = $multi + 4         # 지연값 바이트 위치
$cur    = $bytes[$immOff]
$target = if ($Revert) { 4 } else { $Latency }

Write-Host ("현재 대전 지연값 = $cur 턴") -ForegroundColor Cyan

if ($cur -eq $target) {
    Write-Host ("이미 적용됨: 지연값 = $target 턴. 변경 없음.") -ForegroundColor Yellow
    exit 0
}

# 백업
$bak = "$ExePath.bak_latency_$(Get-Date -Format yyyyMMdd_HHmmss)"
[IO.File]::WriteAllBytes($bak, $bytes)

$bytes[$immOff] = [byte]$target
[IO.File]::WriteAllBytes($ExePath, $bytes)

if ($Revert) {
    Write-Host ("되돌림 완료: 대전 지연값 $cur -> 4 (원래값).") -ForegroundColor Green
} else {
    Write-Host ("적용 완료: 대전 지연값 $cur -> $target 턴. 클릭 반응이 빨라집니다.") -ForegroundColor Green
    Write-Host ("백업: $bak") -ForegroundColor DarkGray
    Write-Host ("멀티플레이는 같이 하는 모든 PC에 같은 값으로 적용하세요.") -ForegroundColor DarkGray
}
