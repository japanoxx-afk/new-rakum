"""경기 자동 기록: 런처가 켜져 있는 동안 게임 메모리를 읽어 리플레이 파일(.rkr)로 저장한다.

파일 = gzip 으로 압축한 JSON 줄:
  1줄: 머리 {"format": 1, "date", "map", "map_rkm"(base64), "players": [...], "types": {...}, "local"}
  나머지: 장면 {"t": 경기 초, "f": 게임 프레임, "k": [유닛 전체] | "c": [바뀐 유닛], "x": [사라진 번호],
               "cmd": [[프레임, 플레이어, base64 명령 묶음]] (게임 엔진 재생용, replay_record_patch),
               "start": {시드, rand, rng, 프레임, 내 번호, 설정} (경기 시작 순간), "chk": [[프레임, rand, LCG, 유닛 해시, 유닛 수]],
               "save": base64 (게임 자체 저장 RKREPLAY.SAV = 시작 상태; 재생할 때 불러옴),
               "p": [[금, 물, 카르마, 글로리, 인구 현재, 인구 최대] * 참가자], "b": [[건물, 만드는 종류, 진행]], "s": [카운터]}
  유닛 = [번호, 종류, 소유, x, y, 체력, 표시]  (표시: 1 건물, 2 건물·금광 안, 4 생산 중)
게임 시계가 멈추면(일시정지·로비) 기록하지 않고, 시계가 줄어들거나 맵이 바뀌면 새 파일을 연다.
"""
from __future__ import annotations

import base64
import datetime
import gzip
import json
import os
import re
import threading
import time
from pathlib import Path

import replay_memory as rm
import replay_record_patch as rrp

FORMAT = 3                     # 2: 명령 기록(cmd)·시드·프레임, 3: 시작 저장·검사값
KEYFRAME_EVERY = 20.0
COUNTERS_EVERY = 5.0
POLL = 0.5


def replay_dir(base_dir) -> Path:
    d = Path(base_dir) / "replays"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _safe(s: str) -> str:
    return re.sub(r'[\\/:*?"<>|\s]+', "_", s).strip("_")[:60] or "map"


def split_records(records) -> dict:
    """링 버퍼 기록 -> 장면 항목: 명령 묶음(플레이어 0..7), 시작(0xFE), 검사값(0xFD)."""
    out = {}
    for f, p, b in records:
        if p == rrp.P_START and len(b) >= rrp.START_LEN:
            out["start"] = rrp.parse_start(b)
        elif p == rrp.P_CHECK and len(b) >= rrp.CHECK_LEN:
            out.setdefault("chk", []).append(rrp.parse_check(b))
        elif p < 8:
            out.setdefault("cmd", []).append([f, p, base64.b64encode(b).decode()])
    return out


class MatchWriter:
    """한 경기의 장면을 파일에 이어 쓴다."""

    def __init__(self, path: Path, header: dict):
        self.path = path
        self.f = gzip.open(path, "wt", encoding="utf-8", compresslevel=6)
        self.f.write(json.dumps(header, ensure_ascii=False, separators=(",", ":")) + "\n")
        self.last_units: dict = {}
        self.last_key = -1e9
        self.last_counters = -1e9
        self.frames = 0
        self.commands = 0

    def frame(self, t: float, units, players, active, gframe=None, cmds=()):
        rows = {u.id: u.row() for u in units if not u.flags & rm.F_IN_PRODUCTION}
        fr = {"t": round(t, 2)}
        if gframe is not None:
            fr["f"] = gframe
        if cmds:
            fr.update(split_records(cmds))
            self.commands += len(fr.get("cmd", ()))
        if t - self.last_key >= KEYFRAME_EVERY:
            fr["k"] = list(rows.values())
            self.last_key = t
        else:
            changed = [r for i, r in rows.items() if self.last_units.get(i) != r]
            gone = [i for i in self.last_units if i not in rows]
            if changed:
                fr["c"] = changed
            if gone:
                fr["x"] = gone
        self.last_units = rows
        fr["p"] = [players[i].resources + list(players[i].pop) for i in active]
        b = [[u.id, prod.type, round(max(0.0, min(1.0, u.progress if u.progress <= 1.5 else u.progress / 100)), 3)]
             for u in units if u.producing for prod in [next((v for v in units if v.id == u.producing), None)] if prod]
        if b:
            fr["b"] = b
        if t - self.last_counters >= COUNTERS_EVERY:
            fr["s"] = [players[i].counters for i in active]
            self.last_counters = t
        self.f.write(json.dumps(fr, separators=(",", ":")) + "\n")
        self.frames += 1
        self.last_t = fr["t"]

    def extra(self, item: dict):
        self.f.write(json.dumps({"t": getattr(self, "last_t", 0.0), **item}, separators=(",", ":")) + "\n")

    def close(self):
        if self.f:
            self.f.close()
            self.f = None
            if self.frames < 4:                     # 너무 짧은 기록(바로 나간 경기)은 남기지 않음
                try:
                    self.path.unlink()
                except OSError:
                    pass


class Recorder:
    """게임 프로세스를 지켜보며 경기마다 리플레이 파일을 만든다."""

    def __init__(self, base_dir, game_dir_fn, open_memory=None, find_pid=None, clock=time.monotonic):
        self.base_dir = base_dir
        self.game_dir_fn = game_dir_fn
        self.open_memory = open_memory or rm.ProcessMemory
        self.find_pid = find_pid or rm.find_game_pid
        self.clock = clock
        self.mem = None
        self.reader = None
        self.writer: MatchWriter | None = None
        self.last_seconds = -1
        self.seconds_at = None                 # 게임 시계가 마지막으로 늘어난 때 (늘어나는 걸 봐야 기록 시작)
        self.map = ""
        self.active: list = []
        self.status = "대기"
        self.cmd_reader = None
        self.pending_cmds: list = []
        self.lost_bytes = 0
        self.save_wait = None                  # (경로, 시작 시각) — 시작 저장 파일을 리플레이에 넣을 때까지
        self.paused_since = None               # 게임 화면 재생 중엔 기록하지 않음
        self.play_flags = None
        self._stop = threading.Event()
        self.thread = None

    def pause_for_playback(self):
        self._finish("재생")
        self.paused_since = time.time()

    def play_status(self) -> str:
        f = self.play_flags
        if not f or not f.get("play"):
            return ""
        if f["diverged"] == 0xFFFFFFFF:
            return "게임 화면 재생: 재생 자료(RKREPLAY.RKP)를 읽지 못했습니다."
        if f["diverged"]:
            sec = f["diverged"] // 30                          # 대전은 30프레임/초 (33ms)
            return (f"게임 화면 재생: {sec // 60}분 {sec % 60:02d}초(프레임 {f['diverged']})부터 원래 경기와 조금 달라졌습니다. "
                    f"명령은 계속 재생하지만(명령 {f['fed']}개) 그 뒤 장면은 원래 경기와 다를 수 있습니다 "
                    f"(선택 명령에서 다른 플레이어의 유닛은 뺍니다).")
        return f"게임 화면 재생 중: 명령 {f['fed']}개 재생, 원래 경기와 같음"

    # ---- 한 번 살펴보기 (테스트에서 직접 부름) ----
    def poll(self):
        if self.paused_since is not None:
            self._poll_playback()
            return
        if self.mem is None:
            pid = self.find_pid()
            if not pid:
                self._finish("게임 꺼짐")
                return
            try:
                self.mem = self.open_memory(pid)
                self.reader = rm.GameReader(self.mem)
            except OSError:
                self.mem = None
                return
            try:
                sec = rrp.find_section(self.mem.read)
                self.cmd_reader = rrp.CommandReader(self.mem.read, sec) if sec else None
                if self.cmd_reader:
                    self.cmd_reader.poll()                 # 기준점: 지금부터 들어오는 명령만
            except OSError:
                self.cmd_reader = None
        try:
            secs = self.reader.play_seconds()
            mapname = self.reader.map_name()
        except OSError:
            self._drop()
            return
        now = self.clock()
        if self.writer and (secs < self.last_seconds or (mapname and mapname != self.map)):
            self._finish("새 경기")
        if self.cmd_reader:
            try:
                cmds, lost = self.cmd_reader.poll()
                self.pending_cmds += cmds
                self.lost_bytes += lost
                for f, p, b in cmds:
                    if p == rrp.P_START and len(b) >= rrp.START_LEN:
                        self._expect_save(rrp.parse_start(b)["local"])
            except OSError:
                pass
        if secs != self.last_seconds:
            if secs > self.last_seconds >= 0:
                self.seconds_at = now
            self.last_seconds = secs
        running = secs > 0 and self.seconds_at is not None and now - self.seconds_at < 2.0 and bool(mapname)
        if not running:
            return
        try:
            players = self.reader.players()
            units = self.reader.units()
        except OSError:
            self._drop()
            return
        active = [p.index for p in players if p.active and p.name]
        if not active:
            return
        if self.writer is None:
            self._start(mapname, players, active)
        t = secs + min(0.99, now - self.seconds_at)
        try:
            gframe = self.reader.frame()
        except OSError:
            gframe = None
        cmds, self.pending_cmds = self.pending_cmds, []
        self.writer.frame(t, units, players, self.active, gframe, cmds)
        self._take_save(now)
        self.status = f"기록 중: {os.path.basename(self.map)} {int(t) // 60}:{int(t) % 60:02d}"

    def _start(self, mapname, players, active):
        self.map, self.active = mapname, active
        rkm = b""
        try:
            gd = self.game_dir_fn()
            p = Path(gd) / mapname.replace("\\", os.sep) if gd else None
            if p and p.is_file():
                rkm = p.read_bytes()
        except OSError:
            pass
        def safe(fn, default):
            try:
                return fn()
            except OSError:
                return default
        types = safe(self.reader.type_table, {})
        local = safe(self.reader.local_player, -1)
        seed = safe(self.reader.seed, None)
        options = safe(lambda: self.reader.options().hex(), "")
        frame0 = safe(self.reader.frame, None)
        rules = safe(self.reader.rules, None)
        stamp = datetime.datetime.now()
        header = {"format": FORMAT, "date": stamp.isoformat(timespec="seconds"), "map": mapname,
                  "map_rkm": base64.b64encode(rkm).decode() if rkm else "",
                  "players": [{"index": i, "name": players[i].name, "race": players[i].race} for i in active],
                  "types": {str(k): v for k, v in types.items()}, "local": local,
                  "seed": seed, "options": options, "frame0": frame0, "commands": self.cmd_reader is not None,
                  "races": [players[i].race for i in range(rm.PLAYER_COUNT)],
                  "slots": [players[i].active for i in range(rm.PLAYER_COUNT)]}
        if rules is not None:
            header["rules"] = rules            # 재생도 이 규칙으로 (선택 한도·집결지 금광 인식)
        name = f"{stamp:%Y%m%d_%H%M%S}_{_safe(Path(mapname.replace(chr(92), '/')).stem)}.rkr"
        self.writer = MatchWriter(replay_dir(self.base_dir) / name, header)

    def _poll_playback(self):
        """재생용으로 띄운 게임: 기록하지 않고 재생 상태만 읽는다. 게임이 끝나면 다시 기록."""
        if self.mem is None:
            pid = self.find_pid()
            if not pid:
                if self.play_flags is not None or time.time() - self.paused_since > 180:
                    self.paused_since, self.play_flags = None, None
                return
            try:
                self.mem = self.open_memory(pid)
                self.reader = rm.GameReader(self.mem)
            except OSError:
                self.mem = None
                return
        try:
            sec = rrp.find_section(self.mem.read)
            self.play_flags = rrp.read_flags(self.mem.read, sec) if sec else {}
        except OSError:
            self._drop()
            self.paused_since, self.play_flags = None, None

    def _expect_save(self, local):
        """게임이 경기 시작에 쓴 RKREPLAY.SAV (<게임>\\USERs\\<내 계정>\\) 를 기다린다."""
        try:
            name = self.reader.players()[local].name if 0 <= local < rm.PLAYER_COUNT else ""
            gd = self.game_dir_fn()
        except (OSError, IndexError):
            return
        if name and gd:
            self.save_wait = (Path(gd) / "USERs" / name / (rrp.SAVE_NAME.decode() + ".SAV"), time.time(), None)

    def _take_save(self, now):
        if not self.save_wait or not self.writer:
            return
        path, since, last_size = self.save_wait
        try:
            st = path.stat()
        except OSError:
            if time.time() - since > 30:
                self.save_wait = None                  # 저장 못 함: 명령만으로는 재생 불가 (기록은 남김)
            return
        if st.st_mtime + 2 < since or st.st_size != last_size:
            self.save_wait = (path, since, st.st_size)  # 크기가 그대로일 때까지 (다 쓸 때까지) 기다림
            return
        self.writer.extra({"save": base64.b64encode(path.read_bytes()).decode(), "save_name": path.name})
        self.save_wait = None

    def _finish(self, why=""):
        if self.writer:
            if self.pending_cmds:                       # 마지막 장면 뒤에 들어온 명령
                self.writer.extra(split_records(self.pending_cmds))
            self.writer.close()
            self.writer = None
        self.pending_cmds = []
        self.save_wait = None
        self.last_seconds = -1
        self.seconds_at = None
        self.status = "대기" if not why else f"대기 ({why})"

    def _drop(self):
        self._finish("게임 꺼짐")
        if self.mem:
            try:
                self.mem.close()
            except OSError:
                pass
        self.mem = self.reader = self.cmd_reader = None

    # ---- 백그라운드 ----
    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self._stop.clear()
        self.thread = threading.Thread(target=self._run, name="replay-recorder", daemon=True)
        self.thread.start()

    def stop(self):
        self._stop.set()
        if self.thread:
            self.thread.join(timeout=3)
        self._drop()

    def _run(self):
        while not self._stop.is_set():
            try:
                self.poll()
                if self.mem is not None and not self.mem.alive():
                    self._drop()
            except Exception:                      # 기록 실패가 런처를 멈추면 안 됨
                self._drop()
            self._stop.wait(POLL)
