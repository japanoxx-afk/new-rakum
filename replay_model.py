"""리플레이 파일(.rkr) 읽기: 장면 복원(키 장면 + 변화), 보간, 통계."""
from __future__ import annotations

import base64
import bisect
import gzip
import json
from dataclasses import dataclass, field
from pathlib import Path

RACES = ("위국군", "아스트리아", "바르바로이")   # 종족 번호 0 무휼(Mu hŭl), 1 아렌(Aren), 2 마르두크(Marduke)
RESOURCE_NAMES = ("금", "물", "카르마", "글로리")
COLORS = ("#e02020", "#2060ff", "#ff9020", "#40c0c0", "#f0f0f0", "#f0e020", "#a040e0", "#20c040")
F_BUILDING, F_INSIDE = 1, 2


@dataclass
class Replay:
    path: Path
    header: dict
    frames: list = field(default_factory=list)
    times: list = field(default_factory=list)
    keys: list = field(default_factory=list)          # 키 장면 위치

    @property
    def duration(self) -> float:
        return self.times[-1] if self.times else 0.0

    @property
    def players(self) -> list:
        return self.header.get("players", [])

    def type_name(self, t) -> str:
        info = self.header.get("types", {}).get(str(t))
        return info["name"] if info else f"#{t}"

    def is_worker(self, t) -> bool:
        info = self.header.get("types", {}).get(str(t))
        return bool(info and info.get("worker"))

    def map_bytes(self) -> bytes:
        s = self.header.get("map_rkm") or ""
        return base64.b64decode(s) if s else b""

    # ---- 장면 ----
    def index_at(self, t: float) -> int:
        return max(0, bisect.bisect_right(self.times, t) - 1)

    def units_at_index(self, i: int) -> dict:
        """번호 -> [번호, 종류, 소유, x, y, 체력, 표시] (i 번째 장면 기준)."""
        k = self.keys[max(0, bisect.bisect_right(self.keys, i) - 1)] if self.keys else 0
        units = {}
        for j in range(k, i + 1):
            fr = self.frames[j]
            if "k" in fr:
                units = {r[0]: r for r in fr["k"]}
            for r in fr.get("c", ()):
                units[r[0]] = r
            for x in fr.get("x", ()):
                units.pop(x, None)
        return units

    def state_at(self, t: float):
        """(유닛 dict, 장면) — 다음 장면과의 위치를 선형 보간."""
        i = self.index_at(t)
        units = self.units_at_index(i)
        if i + 1 < len(self.frames):
            t0, t1 = self.times[i], self.times[i + 1]
            a = 0.0 if t1 <= t0 else max(0.0, min(1.0, (t - t0) / (t1 - t0)))
            if a > 0:
                nxt = self.frames[i + 1]
                moved = {r[0]: r for r in nxt.get("c", ())} if "k" not in nxt else {r[0]: r for r in nxt["k"]}
                out = {}
                for uid, r in units.items():
                    n = moved.get(uid)
                    if n and n[1] == r[1]:
                        r = r[:3] + [round(r[3] + (n[3] - r[3]) * a), round(r[4] + (n[4] - r[4]) * a)] + r[5:]
                    out[uid] = r
                units = out
        return units, self.frames[i]

    def last_value(self, i: int, key: str):
        for j in range(i, -1, -1):
            if key in self.frames[j]:
                return self.frames[j][key]
        return None


def map_state(rp: Replay, game_dir) -> tuple:
    """게임 화면 재생에 쓸 맵 파일: ('ok'|'missing'|'differs'|'unknown', 경로).
    시작 저장은 맵 이름만 담고 있어서, 게임 폴더에 그 맵이 없으면 '맵 없다' 창이 뜨고 게임이 끝난다."""
    name = (rp.header.get("map") or "").replace("\\", "/")
    data = rp.map_bytes()
    if not name or not data:
        return "unknown", None
    path = Path(game_dir) / name
    try:
        cur = path.read_bytes()
    except FileNotFoundError:
        return "missing", path
    except OSError:
        return "unknown", path
    return ("ok" if cur == data else "differs"), path


def install_map(rp: Replay, path: Path) -> None:
    """리플레이에 든 맵을 게임 폴더에 쓴다. 같은 이름의 다른 맵이 있으면 <이름>.bak 으로 보관한다."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        bak = path.with_name(path.name + ".bak")
        if not bak.exists():
            path.replace(bak)
    path.write_bytes(rp.map_bytes())


def ingame_data(rp: Replay):
    """게임 화면 재생 자료: {'start', 'save', 'records'} 또는 무엇이 없는지 알려 주는 문자열.
    records = [(프레임, 플레이어, 바이트)], 같은 프레임에서는 검사값(턴 처리 시작) -> 명령 순서 (기록과 같음)."""
    import struct
    import replay_record_patch as rrp
    start = next((fr["start"] for fr in rp.frames if "start" in fr), None)
    save = next((fr["save"] for fr in rp.frames if "save" in fr), None)
    if not start:
        return "경기 시작 기록이 없습니다 (v0.9054 이상 런처로 기록한 경기만 재생할 수 있습니다)."
    if not save:
        return "경기 시작 저장이 없습니다. 리플레이 탭의 '경기 시작 저장'을 켜고 새로 기록한 경기만 재생할 수 있습니다."
    items = []
    for fr in rp.frames:
        for c in fr.get("chk", ()):
            items.append((c[0], 0, len(items), rrp.P_CHECK, struct.pack(rrp.CHECK_FMT, *[v & 0xFFFFFFFF for v in c[:5]])))
        for f, p, b in fr.get("cmd", ()):
            items.append((f, 1, len(items), p, base64.b64decode(b)))
    items.sort(key=lambda x: (x[0], x[1], x[2]))
    if not any(x[1] == 1 for x in items):
        return "명령 기록이 없습니다."
    return {"start": start, "save": base64.b64decode(save), "records": [(f, p, b) for f, _, _, p, b in items]}


def load(path) -> Replay:
    path = Path(path)
    with gzip.open(path, "rt", encoding="utf-8") as f:
        header = json.loads(f.readline())
        rp = Replay(path, header)
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                fr = json.loads(line)
            except ValueError:
                break                                   # 기록 중 꺼져 잘린 마지막 줄
            if "k" in fr:
                rp.keys.append(len(rp.frames))
            rp.frames.append(fr)
            rp.times.append(fr["t"])
    if not rp.keys and rp.frames:
        rp.keys.append(0)
    return rp


def load_header(path) -> tuple[dict, float]:
    """목록용: 머리와 길이(마지막 장면 시간)만 빠르게."""
    with gzip.open(path, "rt", encoding="utf-8") as f:
        header = json.loads(f.readline())
        last = 0.0
        for line in f:
            if '"t":' in line[:20]:
                try:
                    last = float(line[5:line.index(",")])
                except ValueError:
                    pass
    return header, last


def fmt_time(t: float) -> str:
    t = int(t)
    return f"{t // 3600}:{t // 60 % 60:02d}:{t % 60:02d}" if t >= 3600 else f"{t // 60}:{t % 60:02d}"


def stats(rp: Replay) -> dict:
    """참가자별 통계와 시간별 그래프 자료."""
    idx = {p["index"]: k for k, p in enumerate(rp.players)}
    out = {p["index"]: {"name": p["name"], "race": RACES[p["race"]] if 0 <= p["race"] < 3 else str(p["race"]),
                        "units": {}, "buildings": {}, "lost_units": 0, "lost_buildings": 0, "killed": 0,
                        "peak_army": 0, "final_resources": [0, 0, 0, 0], "pop": (0, 0),
                        "army": [], "workers": [], "resources": []} for p in rp.players}
    seen, alive = {}, {}
    step = max(1, len(rp.frames) // 400)                # 그래프 점 400개 정도
    for i, fr in enumerate(rp.frames):
        if "k" in fr:
            current = {r[0]: r for r in fr["k"]}
            for uid in list(alive):
                if uid not in current:
                    _death(out, alive.pop(uid))
            changed = fr["k"]
        else:
            changed = fr.get("c", ())
            for uid in fr.get("x", ()):
                if uid in alive:
                    _death(out, alive.pop(uid))
        for r in changed:
            uid, typ, owner = r[0], r[1], r[2]
            if (uid, typ) not in seen and owner in out and i > 0:
                bucket = out[owner]["buildings" if r[6] & F_BUILDING else "units"]
                name = rp.type_name(typ)
                bucket[name] = bucket.get(name, 0) + 1
            seen[(uid, typ)] = True
            alive[uid] = r
        if i % step == 0 or i == len(rp.frames) - 1:
            army = {p: 0 for p in out}
            workers = {p: 0 for p in out}
            for r in alive.values():
                if r[2] in out and not r[6] & F_BUILDING:
                    (workers if rp.is_worker(r[1]) else army)[r[2]] += 1
            for p in out:
                out[p]["army"].append((fr["t"], army[p]))
                out[p]["workers"].append((fr["t"], workers[p]))
                out[p]["peak_army"] = max(out[p]["peak_army"], army[p])
            res = fr.get("p")
            if res:
                for p, k in idx.items():
                    if k < len(res):
                        out[p]["resources"].append((fr["t"], res[k][:4]))
    last_p = rp.last_value(len(rp.frames) - 1, "p") if rp.frames else None
    if last_p:
        for p, k in idx.items():
            if k < len(last_p):
                out[p]["final_resources"] = last_p[k][:4]
                out[p]["pop"] = tuple(last_p[k][4:6])
    return {"players": out, "duration": rp.duration}


def _death(out, r):
    owner = r[2]
    if owner in out:
        out[owner]["lost_buildings" if r[6] & F_BUILDING else "lost_units"] += 1


def summary_text(rp: Replay) -> str:
    st = stats(rp)
    lines = [f"맵: {Path(rp.header.get('map', '').replace(chr(92), '/')).stem}    길이: {fmt_time(st['duration'])}    "
             f"날짜: {rp.header.get('date', '').replace('T', ' ')}", ""]
    for p in st["players"].values():
        units = sum(p["units"].values())
        top = ", ".join(f"{k} {v}" for k, v in sorted(p["units"].items(), key=lambda kv: -kv[1])[:6])
        blds = ", ".join(f"{k} {v}" for k, v in sorted(p["buildings"].items(), key=lambda kv: -kv[1])[:6])
        res = "  ".join(f"{n} {v}" for n, v in zip(RESOURCE_NAMES, p["final_resources"]))
        lines += [f"■ {p['name']} ({p['race']})",
                  f"   생산 유닛 {units}  ({top or '-'})",
                  f"   지은 건물 {sum(p['buildings'].values())}  ({blds or '-'})",
                  f"   잃은 유닛 {p['lost_units']}   잃은 건물 {p['lost_buildings']}   최대 병력 {p['peak_army']}",
                  f"   마지막 자원  {res}   인구 {p['pop'][0]}/{p['pop'][1]}", ""]
    return "\n".join(lines)
