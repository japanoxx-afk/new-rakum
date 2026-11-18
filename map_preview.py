"""런처 '맵 미리보기' 탭용 맵 렌더러 (Pillow 불필요).

맵 에디터의 미니맵과 같은 방식: 각 지형 타일을 그 타일의 평균색으로 칠하고
자원(금·우물), 언덕 입구·다리, 시작 위치를 표시한다.
타일 평균색은 map_preview_colors.json (4개 맵 속성, 상하대칭 모드 타일 포함).
"""
from __future__ import annotations

import json
import os
import struct
from dataclasses import dataclass, field
from pathlib import Path

from rkm_format import RkmMap

TILESET_NAMES = ("늪지", "설원", "유적", "던전")
GOLD_IDS = {0: 21, 1: 18, 2: 18, 3: 11}
WELL_IDS = {0: 20, 1: 17, 2: 17, 3: 10}
PLAYER_COLORS = ("#e03c3c", "#3c78e0", "#3cc85a", "#e6c83c", "#b450dc", "#3cc8c8", "#f08c32", "#f0f0f0")
KIND_SUB, KIND_DECO, KIND_RES = 3, 5, 7

_COLORS: dict[int, list[str]] | None = None


def _colors(resource_dir) -> dict[int, list[str]]:
    global _COLORS
    if _COLORS is None:
        p = Path(resource_dir) / "map_preview_colors.json"
        raw = json.loads(p.read_text(encoding="utf-8"))
        _COLORS = {int(k): ["#" + c for c in v] for k, v in raw.items()}
    return _COLORS


def list_maps(game_dir) -> list[str]:
    """Data\\Maps 기준 상대 경로 목록 (하위 폴더 포함, 이름순)."""
    maps = Path(game_dir) / "Data" / "Maps"
    if not maps.is_dir():
        return []
    out = [str(p.relative_to(maps)) for p in maps.rglob("*") if p.is_file() and p.suffix.lower() == ".rkm"]
    return sorted(out, key=lambda s: (s.count(os.sep), s.lower()))


@dataclass
class MapInfo:
    name: str
    tileset: int
    width: int
    height: int
    players: list = field(default_factory=list)     # [(x, y)]
    gold: list = field(default_factory=list)        # [(x, y, amount)]
    wells: list = field(default_factory=list)
    subs: list = field(default_factory=list)        # [(id, x, y)]
    decos: int = 0
    objects: list = field(default_factory=list)     # [(id, x, y)] 자원·장식 (스프라이트 그리기용)
    tiles: list = field(default_factory=list)       # tile index per record, row-major (columns x rows)
    columns: int = 0
    rows: int = 0

    @property
    def tileset_name(self):
        return TILESET_NAMES[self.tileset] if 0 <= self.tileset < 4 else f"#{self.tileset}"

    @property
    def playable(self):
        return max(0, self.width - 8), max(0, self.height - 8)


def load(path) -> MapInfo:
    data = Path(path).read_bytes()
    m = RkmMap(data)
    s0 = m.sections[0][0]
    ts = struct.unpack_from("<I", m.data, s0)[0]
    info = MapInfo(Path(path).name, ts, m.width, m.height, columns=m.columns, rows=m.rows)
    try:
        info.players = m.start_points()
    except ValueError:
        info.players = []
    info.tiles = [struct.unpack_from("<H", m.data, m.start + i * 5)[0] for i in range(m.columns * m.rows)]
    for r in m.objects()[m.object_counts[0]:]:
        kind, oid = r[2], struct.unpack_from("<H", r, 4)[0]
        x, y, val = struct.unpack_from("<III", r, 8)
        if kind in (KIND_RES, KIND_DECO):
            info.objects.append((oid, x, y))
        if kind == KIND_RES:
            (info.gold if (r[6] == 1 or oid == GOLD_IDS.get(ts)) else info.wells).append((x, y, val))
        elif kind == KIND_SUB:
            info.subs.append((oid, x, y))
        elif kind == KIND_DECO:
            info.decos += 1
    return info


def _tile_at(info: MapInfo, wx: float, wy: float) -> int:
    """월드 좌표(px)의 타일 기록 번호. 타일 (x,y) 중심 = (x*256 + (y&1)*128, y*64), 반폭 128x64."""
    best, bd = -1, 9.0
    ty0 = int(wy // 64)
    for ty in (ty0, ty0 + 1):
        if not 0 <= ty < info.rows:
            continue
        off = (ty & 1) * 128
        tx = int(round((wx - off) / 256.0))
        for x in (tx - 1, tx, tx + 1):
            if not 0 <= x < info.columns:
                continue
            d = abs(wx - (x * 256 + off)) / 128.0 + abs(wy - ty * 64) / 64.0
            if d < bd:
                bd, best = d, ty * info.columns + x
    return best


def render_rows(info: MapInfo, resource_dir, size: int = 360):
    """(w, h, rows) — rows 는 Tk PhotoImage.put 형식 문자열 목록. 게임에서 보이는 영역(가장자리 4칸 제외)."""
    pal = _colors(resource_dir).get(info.tileset) or _colors(resource_dir)[0]
    x0, y0 = 4 * 32, 4 * 32
    ww, wh = max(32, (info.width - 8) * 32), max(32, (info.height - 8) * 32)
    s = size / max(ww, wh)
    w, h = max(1, int(ww * s)), max(1, int(wh * s))
    rows = []
    for py in range(h):
        wy = y0 + (py + 0.5) / s
        line = []
        for px in range(w):
            k = _tile_at(info, x0 + (px + 0.5) / s, wy)
            t = info.tiles[k] if k >= 0 else -1
            line.append(pal[t] if 0 <= t < len(pal) else "#000000")
        rows.append("{" + " ".join(line) + "}")
    return w, h, rows, s


def to_px(info: MapInfo, s: float, x: float, y: float):
    """맵 칸 좌표 -> 미리보기 픽셀 좌표."""
    return (x * 32 + 16 - 128) * s, (y * 32 + 16 - 128) * s


def summary(info: MapInfo) -> str:
    pw, ph = info.playable
    gold_total = sum(v for *_, v in info.gold)
    lines = [
        f"{info.tileset_name}  ·  {pw} × {ph}  ·  {len(info.players)}인",
        f"금광 {len(info.gold)}개" + (f" (매장량 {gold_total:,})" if gold_total else "") + f"  ·  우물 {len(info.wells)}개",
        f"언덕 입구·다리 {len(info.subs)}개  ·  장식물·나무 {info.decos}개",
    ]
    if any(i >= 8 for i, *_ in info.subs):
        lines.append("※ 상하대칭 언덕 입구 사용 — 모든 PC에 타일 모드 필요")
    return "\n".join(lines)


# ---------------------------------------------------------------- 실제 타일 그림 미리보기 (Tk)
_ATLAS_META = None
_ATLAS_IMG = {}


def _atlas_meta(resource_dir):
    global _ATLAS_META
    if _ATLAS_META is None:
        _ATLAS_META = json.loads((Path(resource_dir) / "map_preview_tiles" / "atlas.json").read_text(encoding="utf-8"))["tilesets"]
    return _ATLAS_META


def pick_scale(info: MapInfo, max_px: int) -> tuple[int, int]:
    """(축소 배율 4|8, 추가 subsample) — 보이는 영역이 max_px 안에 들도록."""
    world = max(info.width - 8, info.height - 8) * 32
    if world / 4 <= max_px:
        return 4, 1
    sub = 1
    while world / (8 * sub) > max_px:
        sub += 1
    return 8, sub


def render_tk(info: MapInfo, resource_dir, master, max_px: int = 560):
    """게임 타일·언덕 입구·오브젝트 그림으로 그린 PhotoImage 와 (배율, subsample) 를 돌려준다."""
    import tkinter as tk
    sc, sub = pick_scale(info, max_px)
    meta = _atlas_meta(resource_dir).get(str(info.tileset)) or _atlas_meta(resource_dir)["0"]
    m = meta[str(sc)]
    key = (info.tileset, sc, str(master))
    atlas = _ATLAS_IMG.get(key)
    if atlas is None:
        atlas = tk.PhotoImage(master=master, file=str(Path(resource_dir) / "map_preview_tiles" / m["file"]))
        _ATLAS_IMG[key] = atlas
    border = 128 // sc                                   # 게임에서 안 보이는 가장자리 4칸
    W = max(1, (info.width - 8) * 32 // sc)
    H = max(1, (info.height - 8) * 32 // sc)
    img = tk.PhotoImage(master=master, width=W, height=H)
    img.put("#000000", to=(0, 0, W, H))
    tcl = master.tk.call
    name, aname = str(img), str(atlas)

    def blit(sx, sy, w, h, dx, dy):
        if dx < 0:
            sx -= dx; w += dx; dx = 0
        if dy < 0:
            sy -= dy; h += dy; dy = 0
        w = min(w, W - dx); h = min(h, H - dy)
        if w > 0 and h > 0:
            tcl(name, "copy", aname, "-from", sx, sy, sx + w, sy + h, "-to", dx, dy, "-compositingrule", "overlay")

    tw, th, cw, ch, per, cnt = 256 // sc, 128 // sc, m["cw"], m["ch"], m["per"], m["count"]
    for i, t in enumerate(info.tiles):
        if not 0 <= t < cnt:
            continue
        x, y = i % info.columns, i // info.columns
        cx = (x * 256 + (y & 1) * 128) // sc - border
        cy = (y * 64) // sc - border
        blit((t % per) * cw, (t // per) * ch, cw, ch, cx - tw // 2 - 1, cy - th // 2 - 1)
    for oid, x, y in info.subs:                          # 언덕 입구·다리: 스프라이트 왼쪽 위 = 앵커
        if 0 <= oid < len(m["sub"]):
            sx, sy, w, h = m["sub"][oid]
            blit(sx, sy, w, h, x * 32 // sc - border, y * 32 // sc - border)
    for oid, x, y in sorted(info.objects, key=lambda o: o[2]):
        if 0 <= oid < len(m["obj"]):
            sx, sy, w, h, ox, oy = m["obj"][oid]
            blit(sx, sy, w, h, x * 32 // sc + ox - border, y * 32 // sc + oy - border)
    if sub > 1:
        img = img.subsample(sub)
    return img, sc * sub


def to_px_scaled(scale: int, x: float, y: float):
    """맵 칸 좌표 -> render_tk 결과 이미지의 픽셀 좌표."""
    return (x * 32 + 16 - 128) / scale, (y * 32 + 16 - 128) / scale
