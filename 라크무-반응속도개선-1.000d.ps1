#Requires -Version 5
<#
  라크무 반응속도 개선 패치 (클라이언트 1.000d 전용)

  사용법:
    1) 게임을 1.000d 까지 업데이트
    2) 게임을 완전히 종료
    3) 이 파일을 마우스 우클릭 -> "PowerShell로 실행" (관리자 권한 권장)

  하는 일:
    1) 명령 지연(lockstep command latency)을 4 -> 1 턴으로 낮춰 클릭 반응을 빠르게 함.
    2) 게임 종료(Quit) 후 결과화면에서 튕기던 크래시를 막아 로비로 정상 복귀시킴.
    - Rhakmu.exe 만 수정. 백업 자동 생성. 서버/다른 파일은 건드리지 않음.

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
$changed = $false
$madeBackup = $false
function Backup-Once {
    if (-not $script:madeBackup) {
        $script:bak = "$ExePath.bak_improve_$(Get-Date -Format yyyyMMdd_HHmmss)"
        [IO.File]::WriteAllBytes($script:bak, $script:bytes)
        $script:madeBackup = $true
    }
}

# ===== (2) 종료 크래시 가드 =====
# 대전이 끝나면 결과화면(form)을 만들어 그리는데, 그 컨트롤의 이미지가 이미 해제되어
# class_form::DrawControl()에서 ACCESS_VIOLATION 으로 튕긴다(통계화면 직후).
# 결과화면 셋업(40바이트: RECT 구성 + 셋업 함수 call)을 NOP 으로 건너뛰면,
# 결과화면을 만들지 않으므로 그리다 죽지 않고 그대로 로비로 복귀한다. (1.000d 검증)
$pgOrig = [byte[]]@(0x83,0xEC,0x10,0x8B,0xCC,0x8B,0x55,0xE8,0x89,0x11,0x8B,0x45,0xEC,0x89,0x41,0x04,0x8B,0x55,0xF0,0x89,0x51,0x08,0x8B,0x45,0xF4,0x89,0x41,0x0C,0x8B,0x4D,0x08,0x51,0x8B,0x4D,0xFC,0xE8,0x98,0xFA,0xFF,0xFF)
# 시그니처(마지막 call의 상대주소 4바이트 제외)로 위치를 찾는다
$pgSig = $pgOrig[0..35]
$pgOff = -1
for ($i = 0; $i -lt $bytes.Length - $pgSig.Length; $i++) {
    $ok = $true
    for ($j = 0; $j -lt $pgSig.Length; $j++) { if ($bytes[$i+$j] -ne $pgSig[$j]) { $ok = $false; break } }
    if ($ok) { $pgOff = $i; break }
}
if ($Revert) {
    Write-Host "종료 크래시 가드: -Revert 시 유지 (완전 원복은 .bak_improve 백업으로)." -ForegroundColor Yellow
} elseif ($pgOff -ge 0) {
    $allNop = $true
    for ($j = 0; $j -lt 40; $j++) { if ($bytes[$pgOff+$j] -ne 0x90) { $allNop = $false; break } }
    if ($allNop) {
        Write-Host "종료 크래시 가드: 이미 적용됨." -ForegroundColor Yellow
    } else {
        Backup-Once
        for ($j = 0; $j -lt 40; $j++) { $bytes[$pgOff+$j] = 0x90 }
        $changed = $true
        Write-Host ("종료 크래시 가드 적용: 결과화면 셋업 스킵 (파일 0x{0:X})." -f $pgOff) -ForegroundColor Green
    }
} else {
    Write-Host "종료 크래시 가드: 대상 코드를 못 찾음 (1.000d가 아닐 수 있음). 건너뜀." -ForegroundColor Yellow
}

# ===== (3) 종료시 메뉴 커서 크래시 가드 (DrawMenuMouse) =====
# 종료 후 CGameMenu::Draw 가 DrawMenuMouse 를 호출하는데, 커서 이미지 매니저
# [0x6E1320]/[0x6E1324] 가 이미 해제(NULL)되어 [ecx+0x14] 참조에서 또 튕긴다.
# 호출부(0x004241C9: call DrawMenuMouse)를 코드케이브로 우회시켜, 매니저가
# NULL 이면 호출을 건너뛰고 정상 복귀한다. (평소 메뉴에선 커서 정상 표시)
$mmSiteOff = 0x000241C9
$mmSiteOrig = [byte[]]@(0xE8,0xC2,0x0C,0x00,0x00)              # call 0x424E90
$mmSiteNew  = [byte[]]@(0xE8,0x44,0x72,0x0C,0x00)              # call cave 0x4EB412
$mmCaveOff  = 0x000EB412
$mmStub = [byte[]]@(0x83,0x3D,0x20,0x13,0x6E,0x00,0x00, 0x74,0x11,
                    0x83,0x3D,0x24,0x13,0x6E,0x00,0x00, 0x74,0x08,
                    0x8B,0x4D,0xFC, 0xE8,0x64,0x9A,0xF3,0xFF, 0xC3)
function ByteEq($arr,$off,$exp){ for($k=0;$k -lt $exp.Length;$k++){ if($arr[$off+$k] -ne $exp[$k]){return $false} } return $true }
if (-not $Revert) {
    if (ByteEq $bytes $mmSiteOff $mmSiteNew) {
        Write-Host "메뉴 커서 크래시 가드: 이미 적용됨." -ForegroundColor Yellow
    } elseif (ByteEq $bytes $mmSiteOff $mmSiteOrig -and (ByteEq $bytes $mmCaveOff @(0,0,0,0,0,0,0,0))) {
        Backup-Once
        for ($k=0;$k -lt $mmStub.Length;$k++){ $bytes[$mmCaveOff+$k]=$mmStub[$k] }
        for ($k=0;$k -lt $mmSiteNew.Length;$k++){ $bytes[$mmSiteOff+$k]=$mmSiteNew[$k] }
        $changed = $true
        Write-Host "메뉴 커서 크래시 가드 적용: DrawMenuMouse NULL 우회." -ForegroundColor Green
    } else {
        Write-Host "메뉴 커서 크래시 가드: 대상/케이브 불일치로 건너뜀 (1.000d 아닐 수 있음)." -ForegroundColor Yellow
    }
}

# ===== (1) 레이턴시 =====
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
    Write-Host ("레이턴시: 이미 $target 턴. 변경 없음.") -ForegroundColor Yellow
} else {
    Backup-Once
    $bytes[$immOff] = [byte]$target
    $changed = $true
    if ($Revert) {
        Write-Host ("레이턴시 되돌림: $cur -> 4 (원래값).") -ForegroundColor Green
    } else {
        Write-Host ("레이턴시 적용: $cur -> $target 턴. 클릭 반응이 빨라집니다.") -ForegroundColor Green
    }
}

# ===== 저장 =====
if ($changed) {
    [IO.File]::WriteAllBytes($ExePath, $bytes)
    Write-Host ""
    Write-Host "완료! 게임을 실행해 확인하세요." -ForegroundColor Green
    Write-Host ("백업: $bak") -ForegroundColor DarkGray
    Write-Host "멀티플레이는 같이 하는 모든 PC에 -Latency 값을 똑같이 적용하세요." -ForegroundColor DarkGray
} else {
    Write-Host ""
    Write-Host "변경 사항 없음 (이미 모두 적용된 상태)." -ForegroundColor Yellow
}
