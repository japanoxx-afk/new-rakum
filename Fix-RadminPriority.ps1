<#
Fix-RadminPriority.ps1
라크무 라드민 멀티 "동기화 실패" 해결 스크립트.

원인: DirectPlay8은 P2P 세션에 "자기 로컬 IP"를 박아 상대에게 알린다.
하마치는 설치 시 자기 어댑터 우선순위(interface metric)를 물리 랜보다 높게
잡아서 25.x가 선택되지만, 라드민은 그렇지 않아 물리 랜(192.168.x)이 선택되고
상대가 라드민망 밖 IP로 접속 시도 → 동기화 실패.

이 스크립트는 라드민(26.x) 어댑터의 metric을 1로 낮춰(=최우선) DP8이 26.x를
자기 IP로 박도록 강제한다. 대전하는 두 PC 모두에서 관리자 권한으로 1번 실행.
게임/라드민 재시작 후 대전하면 됨. (되돌리려면 -Revert)
#>
param([switch]$Revert)

$ErrorActionPreference = "Stop"

# 관리자 권한 확인
$isAdmin = ([Security.Principal.WindowsPrincipal] `
    [Security.Principal.WindowsIdentity]::GetCurrent()
).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "관리자 권한으로 다시 실행하세요 (PowerShell 우클릭 > 관리자 권한으로 실행)." -ForegroundColor Red
    exit 1
}

# 라드민 어댑터 찾기 (26.x IPv4를 가진 어댑터)
$radmin = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object { $_.IPAddress -like "26.*" } |
    Select-Object -First 1

if (-not $radmin) {
    Write-Host "26.x (라드민) IP를 가진 어댑터를 찾지 못했습니다. 라드민 VPN이 켜져 있는지 확인하세요." -ForegroundColor Red
    exit 1
}

$idx   = $radmin.InterfaceIndex
$alias = (Get-NetAdapter -InterfaceIndex $idx).Name
Write-Host "라드민 어댑터: '$alias'  (IP $($radmin.IPAddress), ifIndex $idx)"

if ($Revert) {
    Set-NetIPInterface -InterfaceIndex $idx -AutomaticMetric Enabled
    Write-Host "되돌림: '$alias' 자동 metric 복원." -ForegroundColor Yellow
    exit 0
}

# 라드민 어댑터를 최우선(metric 1)으로
Set-NetIPInterface -InterfaceIndex $idx -InterfaceMetric 1
Write-Host "적용: '$alias' InterfaceMetric = 1 (최우선)" -ForegroundColor Green

Write-Host ""
Write-Host "완료. 라드민과 게임을 재시작한 뒤 대전하세요." -ForegroundColor Cyan
Write-Host "현재 IPv4 인터페이스 우선순위:" -ForegroundColor DarkGray
Get-NetIPInterface -AddressFamily IPv4 |
    Sort-Object InterfaceMetric |
    Format-Table ifIndex, InterfaceAlias, InterfaceMetric, ConnectionState -AutoSize
