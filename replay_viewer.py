"""리플레이 보기 창 (Tk).

  1 / 2 / 4   재생 속도 1배 / 2배 / 4배      Space  일시정지      ← / →  10초 뒤로 / 앞으로
  Esc         리플레이 종료                  휠      확대·축소      오른쪽 드래그  화면 이동
  유닛·건물 클릭  정보 (상대 건물도 생산 중인 유닛·진행 표시)      S  통계 창
맵은 전부 밝혀서 보여 준다 (시야 제한 없음). 오른쪽 위에 참가자 자원·인구.
"""
from __future__ import annotations

import math
import os
import tempfile
import time
import tkinter as tk
from tkinter import ttk

import replay_model as M

SPEEDS = {"1": 1.0, "2": 2.0, "4": 4.0}
TICK_MS = 50


class ReplayViewer(tk.Toplevel):
    def __init__(self, master, path, resource_dir=None, autoplay=True):
        super().__init__(master)
        self.rp = M.load(path)
        self.resource_dir = resource_dir
        self.title(f"리플레이 — {os.path.basename(str(path))}")
        self.geometry("1100x760")
        self.configure(bg="#101010")
        self.t = 0.0
        self.speed = 1.0
        self.playing = autoplay
        self.zoom = 1.0
        self.pan = [0.0, 0.0]
        self.selected = None
        self._last = time.monotonic()
        self._drag = None
        self._map_img = None
        self._scaled = None
        self._scaled_zoom = None
        self.map_info = None
        self.scale = 8
        self.world_w = self.world_h = 4096
        self._load_map()
        self.colors = {p["index"]: M.COLORS[p["index"] % len(M.COLORS)] for p in self.rp.players}

        self.cv = tk.Canvas(self, bg="#000000", highlightthickness=0)
        self.cv.pack(fill="both", expand=True)
        bar = ttk.Frame(self)
        bar.pack(fill="x")
        self.play_btn = ttk.Button(bar, text="⏸", width=3, command=self.toggle)
        self.play_btn.pack(side="left", padx=4, pady=3)
        self.speed_var = tk.StringVar(value="1배")
        ttk.Label(bar, textvariable=self.speed_var, width=5).pack(side="left")
        self.pos = tk.DoubleVar(value=0)
        self.slider = ttk.Scale(bar, from_=0, to=max(1.0, self.rp.duration), variable=self.pos,
                                command=lambda v: self.seek(float(v), from_slider=True))
        self.slider.pack(side="left", fill="x", expand=True, padx=6)
        self.time_var = tk.StringVar()
        ttk.Label(bar, textvariable=self.time_var, width=14).pack(side="left")
        ttk.Label(bar, text="1·2·4 속도  Space 정지  ←→ 10초  S 통계  Esc 종료", style="Muted.TLabel").pack(side="left", padx=6)

        for k in SPEEDS:
            self.bind(k, lambda e, k=k: self.set_speed(SPEEDS[k]))
        self.bind("<space>", lambda e: self.toggle())
        self.bind("<Escape>", lambda e: self.close())
        self.bind("<Left>", lambda e: self.seek(self.t - 10))
        self.bind("<Right>", lambda e: self.seek(self.t + 10))
        self.bind("s", lambda e: self.show_stats())
        self.bind("S", lambda e: self.show_stats())
        self.cv.bind("<Button-1>", self.click)
        self.cv.bind("<MouseWheel>", self.wheel)
        self.cv.bind("<ButtonPress-3>", lambda e: setattr(self, "_drag", (e.x, e.y, *self.pan)))
        self.cv.bind("<B3-Motion>", self.drag)
        self.cv.bind("<Configure>", lambda e: self.draw())
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.focus_force()
        self._job = self.after(TICK_MS, self.tick)

    # ---- 맵 ----
    def _load_map(self):
        data = self.rp.map_bytes()
        if not data:
            return
        try:
            import map_preview
            with tempfile.NamedTemporaryFile(suffix=".rkm", delete=False) as f:
                f.write(data)
                tmp = f.name
            try:
                self.map_info = map_preview.load(tmp)
            finally:
                os.unlink(tmp)
            self.world_w = (self.map_info.width - 8) * 32
            self.world_h = (self.map_info.height - 8) * 32
            if self.resource_dir:
                self._map_img, self.scale = map_preview.render_tk(self.map_info, self.resource_dir, self, 1400)
        except Exception:
            self._map_img = None

    def _view(self):
        w, h = max(1, self.cv.winfo_width()), max(1, self.cv.winfo_height())
        fit = min(w / self.world_w, h / self.world_h)
        z = fit * self.zoom
        if self._map_img is not None:              # Tk 그림은 정수배로만 늘이고 줄임: 맵과 유닛이 어긋나지 않게 맞춤
            f = z * self.scale
            f = max(1, math.floor(f)) if f >= 1 else 1 / math.ceil(1 / f - 1e-9)   # 내림: 창 안에 다 들어오게
            z = f / self.scale
        ox = (w - self.world_w * z) / 2 + self.pan[0]
        oy = (h - self.world_h * z) / 2 + self.pan[1]
        return z, ox, oy

    def to_screen(self, x, y):
        z, ox, oy = self._view()
        return ox + (x - 128) * z, oy + (y - 128) * z           # 가장자리 4칸(128px)은 게임에서도 안 보임

    def to_world(self, sx, sy):
        z, ox, oy = self._view()
        return (sx - ox) / z + 128, (sy - oy) / z + 128

    # ---- 재생 ----
    def tick(self):
        now = time.monotonic()
        dt, self._last = now - self._last, now
        if self.playing:
            self.t = min(self.rp.duration, self.t + dt * self.speed)
            if self.t >= self.rp.duration:
                self.playing = False
                self.play_btn.configure(text="▶")
        self.draw()
        self._job = self.after(TICK_MS, self.tick)

    def toggle(self):
        if not self.playing and self.t >= self.rp.duration:
            self.t = 0
        self.playing = not self.playing
        self.play_btn.configure(text="⏸" if self.playing else "▶")

    def set_speed(self, s):
        self.speed = s
        self.speed_var.set(f"{s:g}배")

    def seek(self, t, from_slider=False):
        self.t = max(0.0, min(self.rp.duration, t))
        if not from_slider:
            self.pos.set(self.t)
        self.draw()

    def close(self):
        try:
            self.after_cancel(self._job)
        except (tk.TclError, ValueError):
            pass
        self.destroy()

    # ---- 그리기 ----
    def draw(self):
        cv = self.cv
        cv.delete("all")
        z, ox, oy = self._view()
        if self._map_img is not None:
            factor = z * self.scale
            if self._scaled_zoom != round(factor, 3):
                self._scaled = self._resized(factor)
                self._scaled_zoom = round(factor, 3)
            if self._scaled is not None:
                cv.create_image(ox, oy, image=self._scaled, anchor="nw")
        else:
            cv.create_rectangle(ox, oy, ox + self.world_w * z, oy + self.world_h * z, fill="#2a2a20", outline="")
        units, fr = self.rp.state_at(self.t)
        prod = {b[0]: b for b in (fr.get("b") or [])}
        r_unit = max(2, min(10, 12 * z))
        for r in sorted(units.values(), key=lambda r: not r[6] & M.F_BUILDING):
            if r[6] & M.F_INSIDE:
                continue
            sx, sy = self.to_screen(r[3], r[4])
            col = self.colors.get(r[2], "#909090")
            if r[6] & M.F_BUILDING:
                s = max(4, min(40, 40 * z))
                cv.create_rectangle(sx - s, sy - s, sx + s, sy + s, fill=col, outline="#000000", stipple="gray50")
                cv.create_rectangle(sx - s, sy - s, sx + s, sy + s, outline=col, width=2)
                if r[0] in prod:
                    cv.create_rectangle(sx - s, sy + s + 2, sx - s + 2 * s * prod[r[0]][2], sy + s + 5, fill="#ffffff", outline="")
            else:
                cv.create_oval(sx - r_unit, sy - r_unit, sx + r_unit, sy + r_unit, fill=col, outline="#000000")
            if self.selected == r[0]:
                cv.create_oval(sx - 14, sy - 14, sx + 14, sy + 14, outline="#ffff40", width=2)
        self._draw_players(fr)
        self._draw_selected(units, prod)
        self.time_var.set(f"{M.fmt_time(self.t)} / {M.fmt_time(self.rp.duration)}")
        if self.playing:
            self.pos.set(self.t)

    def _resized(self, factor):
        img = self._map_img
        if factor <= 0:
            return None
        if abs(factor - 1) < 0.05:
            return img
        if factor > 1:
            k = min(8, max(1, int(round(factor))))
            return img.zoom(k) if k > 1 else img
        k = max(1, int(round(1 / factor)))
        return img.subsample(k)

    def _draw_players(self, fr):
        cv = self.cv
        i = self.rp.index_at(self.t)
        res = fr.get("p") or self.rp.last_value(i, "p") or []
        w = cv.winfo_width()
        x0, y = w - 330, 8
        h = 18 + 34 * len(self.rp.players)
        cv.create_rectangle(x0 - 6, y - 4, w - 6, y + h, fill="#000000", outline="#606060", stipple="gray75")
        for k, p in enumerate(self.rp.players):
            col = self.colors.get(p["index"], "#ffffff")
            race = M.RACES[p["race"]] if 0 <= p["race"] < 3 else "?"
            cv.create_rectangle(x0, y + 3, x0 + 10, y + 13, fill=col, outline="")
            cv.create_text(x0 + 16, y, text=f"{p['name']} ({race})", anchor="nw", fill="#ffffff", font=("Malgun Gothic", 10, "bold"))
            if k < len(res):
                v = res[k]
                line = "  ".join(f"{n} {v[j]}" for j, n in enumerate(M.RESOURCE_NAMES)) + f"  인구 {v[4]}/{v[5]}"
                cv.create_text(x0 + 16, y + 16, text=line, anchor="nw", fill="#e0e0a0", font=("Malgun Gothic", 9))
            y += 34

    def _draw_selected(self, units, prod):
        r = units.get(self.selected)
        if not r:
            return
        owner = next((p for p in self.rp.players if p["index"] == r[2]), None)
        info = self.rp.header.get("types", {}).get(str(r[1]), {})
        lines = [f"{self.rp.type_name(r[1])}  ({owner['name'] if owner else '?'})",
                 f"체력 {r[5]}" + (f" / {info['max_hp']}" if info.get("max_hp") else "")]
        if r[0] in prod:
            b = prod[r[0]]
            lines.append(f"생산 중: {self.rp.type_name(b[1])}  {int(b[2] * 100)}%")
        elif r[6] & M.F_BUILDING:
            lines.append("생산 중인 유닛 없음")
        cv = self.cv
        y = cv.winfo_height() - 16 - 18 * len(lines)
        cv.create_rectangle(8, y - 6, 330, cv.winfo_height() - 8, fill="#000000", outline="#606060", stipple="gray75")
        for k, s in enumerate(lines):
            cv.create_text(16, y + 18 * k, text=s, anchor="nw", fill="#ffffff", font=("Malgun Gothic", 10))

    # ---- 입력 ----
    def click(self, e):
        units, _ = self.rp.state_at(self.t)
        wx, wy = self.to_world(e.x, e.y)
        best, bd = None, 1e18
        for r in units.values():
            if r[6] & M.F_INSIDE:
                continue
            d = (r[3] - wx) ** 2 + (r[4] - wy) ** 2
            lim = (64 if r[6] & M.F_BUILDING else 32) ** 2
            if d < bd and d < lim * max(1, 1 / self._view()[0] / 8) ** 2:
                best, bd = r[0], d
        self.selected = best
        self.draw()

    def wheel(self, e):
        old = self.zoom
        self.zoom = max(1.0, min(8.0, self.zoom * (1.25 if e.delta > 0 else 0.8)))
        if self.zoom != old:                           # 커서 위치 기준 확대
            w, h = self.cv.winfo_width(), self.cv.winfo_height()
            k = self.zoom / old
            self.pan[0] = e.x - (e.x - (w / 2 + self.pan[0])) * k - w / 2
            self.pan[1] = e.y - (e.y - (h / 2 + self.pan[1])) * k - h / 2
            if self.zoom == 1.0:
                self.pan = [0.0, 0.0]
        self.draw()

    def drag(self, e):
        if self._drag:
            x0, y0, px, py = self._drag
            self.pan = [px + e.x - x0, py + e.y - y0]
            self.draw()

    def show_stats(self):
        StatsWindow(self, self.rp)


class StatsWindow(tk.Toplevel):
    """통계: 요약 글 + 병력·일꾼·자원(금) 그래프."""

    def __init__(self, master, rp):
        super().__init__(master)
        self.title("리플레이 통계")
        self.geometry("760x620")
        st = M.stats(rp)
        txt = tk.Text(self, height=14, wrap="word", bg="#1b1b1b", fg="#e8e8e8", relief="flat", font=("Malgun Gothic", 10))
        txt.insert("1.0", M.summary_text(rp))
        txt.configure(state="disabled")
        txt.pack(fill="x", padx=8, pady=8)
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        for title, key, pick in (("병력(일꾼 제외)", "army", lambda v: v), ("일꾼", "workers", lambda v: v),
                                 ("금", "resources", lambda v: v[0]), ("물", "resources", lambda v: v[1])):
            cv = tk.Canvas(nb, bg="#121212", highlightthickness=0)
            nb.add(cv, text=title)
            cv.bind("<Configure>", lambda e, cv=cv, key=key, pick=pick: draw_chart(cv, st, key, pick))
        self.bind("<Escape>", lambda e: self.destroy())


def draw_chart(cv, st, key, pick):
    cv.delete("all")
    w, h = cv.winfo_width(), cv.winfo_height()
    if w < 50 or h < 50:
        return
    series = [(idx, p, [(t, pick(v)) for t, v in p[key]]) for idx, p in st["players"].items()]
    tmax = max([st["duration"], 1])
    vmax = max([v for _, _, s in series for _, v in s] + [1])
    L, B = 50, h - 30
    cv.create_line(L, 10, L, B, fill="#606060")
    cv.create_line(L, B, w - 10, B, fill="#606060")
    for k in range(5):
        v = vmax * k / 4
        y = B - (B - 10) * k / 4
        cv.create_text(L - 6, y, text=f"{int(v)}", anchor="e", fill="#a0a0a0", font=("Malgun Gothic", 8))
    for k in range(5):
        t = tmax * k / 4
        x = L + (w - 10 - L) * k / 4
        cv.create_text(x, B + 12, text=M.fmt_time(t), fill="#a0a0a0", font=("Malgun Gothic", 8))
    for n, (idx, p, s) in enumerate(series):
        col = M.COLORS[idx % len(M.COLORS)]
        pts = []
        for t, v in s:
            pts += [L + (w - 10 - L) * t / tmax, B - (B - 10) * v / vmax]
        if len(pts) >= 4:
            cv.create_line(*pts, fill=col, width=2)
        cv.create_text(w - 14, 14 + 16 * n, text=p["name"], anchor="ne", fill=col, font=("Malgun Gothic", 9, "bold"))
