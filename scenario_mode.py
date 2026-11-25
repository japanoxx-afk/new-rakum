"""패키지(오프라인) 모드로 게임 실행 — 메인 메뉴·싱글 시나리오 화면 진입 (실험).

분석 (Rhakmu.exe 1.000d):
  시작할 때 0x4D9990 이 명령줄을 본다. '/ENC…'(한게임 웹에서 넘긴 아이디·암호)가 아니면 0x4DD130(0, 0, 0) 을 부르고,
  0x4DD130 은 0x4DD1F0 으로 레지스트리 HKLM\\SOFTWARE\\TriggerSoft\\RhakMu 의 값 "Pack" 을 읽는다 (0x425AD0):
    Pack == 0 (한게임 내려받기판, 지금 설치본)  -> [0x106AE62] = 0x1100 : 온라인(TNet) 로그인 화면으로만 간다.
    Pack != 0 (패키지판)                        -> [0x106AE62] = 0x11   : 오프라인 메인 메뉴 (skip.txt 가 0 이면 먼저 여는 화면).
  게임 방식은 [0x6E167E] (0 커스텀, 1 시나리오, 2 랜, 3 TNet) 이고, 시나리오를 시작하면 0x419B60 이
  "DATA\\Scenario\\Scenario-%d-%d.rkm" (단계 [메뉴+0x30A], 진영 0/1 [메뉴+0x30C]) 을 맵으로 연다.
  설치본에는 Data\\Scenario 폴더와 시나리오 맵이 없다.

그래서 실행 파일은 건드리지 않고:
  1) 게임을 띄우기 전에 Pack 을 1 로 바꾸고 (예전 값은 런처 설정에 적어 두었다가 다음 보통 실행 때 되돌린다),
  2) 시나리오 맵 자리에 사용자가 고른 대전 맵을 복사해 둔다 (이미 있는 파일은 건드리지 않는다).
실제 미션(목표·대화)은 없다. 시나리오 화면이 열리고 맵이 시작되는지 보는 실험용.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

REGISTRY_KEY = r"SOFTWARE\TriggerSoft\RhakMu"
VALUE = "Pack"
STAGES, SIDES = range(0, 3), range(0, 2)      # 처음 단계 번호가 0 인지 1 인지 몰라 0~2 를 모두 둔다
MANIFEST = "launcher_scenario.json"           # 런처가 만든 파일 목록 (되돌릴 때 이것만 지운다)


def _registry(winreg):
    if winreg is None:
        import winreg
    return winreg


def get_pack(winreg=None):
    """지금 Pack 값. 키나 값이 없으면 None."""
    winreg = _registry(winreg)
    access = winreg.KEY_READ | getattr(winreg, "KEY_WOW64_32KEY", 0)      # 32비트 게임이 보는 키
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, REGISTRY_KEY, 0, access) as key:
            value, kind = winreg.QueryValueEx(key, VALUE)
    except OSError:
        return None
    return value if kind == winreg.REG_DWORD else None


def set_pack(value, winreg=None) -> None:
    """Pack 값을 쓴다 (None 이면 값을 지운다). 키가 없으면 만든다. 실패하면 OSError."""
    winreg = _registry(winreg)
    access = winreg.KEY_READ | winreg.KEY_WRITE | getattr(winreg, "KEY_WOW64_32KEY", 0)
    with winreg.CreateKeyEx(winreg.HKEY_LOCAL_MACHINE, REGISTRY_KEY, 0, access) as key:
        if value is None:
            try:
                winreg.DeleteValue(key, VALUE)
            except OSError:
                pass
        else:
            winreg.SetValueEx(key, VALUE, 0, winreg.REG_DWORD, int(value))


def enable(winreg=None):
    """패키지 모드로. 돌려놓을 예전 값(없었으면 None)을 돌려준다."""
    before = get_pack(winreg)
    if before != 1:
        set_pack(1, winreg)
    return before


def restore(before, winreg=None) -> None:
    """enable() 이 돌려준 값으로 되돌린다."""
    if get_pack(winreg) != before:
        set_pack(before, winreg)


def scenario_dir(game_dir) -> Path:
    return Path(game_dir) / "Data" / "Scenario"


def install_maps(game_dir, source) -> list[str]:
    """시나리오 맵 자리(Scenario-단계-진영.rkm)에 source 맵을 복사한다. 이미 있는 남의 파일은 그대로 둔다.
    런처가 넣은 파일은 MANIFEST 에 적어 두고, 다시 부르면 그 파일들만 새 맵으로 바꾼다. 넣은 파일 이름 목록을 돌려준다."""
    source = Path(source)
    if not source.is_file():
        raise FileNotFoundError(str(source))
    folder = scenario_dir(game_dir)
    folder.mkdir(parents=True, exist_ok=True)
    manifest = folder / MANIFEST
    try:
        ours = set(json.loads(manifest.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        ours = set()
    written = []
    for stage in STAGES:
        for side in SIDES:
            name = f"Scenario-{stage}-{side}.rkm"
            target = folder / name
            if target.exists() and name not in ours:
                continue
            shutil.copyfile(source, target)
            written.append(name)
    manifest.write_text(json.dumps(sorted(ours | set(written))), encoding="utf-8")
    return written


def remove_maps(game_dir) -> list[str]:
    """런처가 넣은 시나리오 맵만 지운다. 폴더가 비면 폴더도 지운다."""
    folder = scenario_dir(game_dir)
    manifest = folder / MANIFEST
    try:
        ours = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    removed = []
    for name in ours:
        target = folder / name
        if target.is_file() and target.parent == folder:
            target.unlink()
            removed.append(name)
    manifest.unlink(missing_ok=True)
    try:
        folder.rmdir()
    except OSError:
        pass
    return removed
