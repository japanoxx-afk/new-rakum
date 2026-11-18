"""런처 UI 테마.

Sun Valley(sv-ttk, Windows 11 스타일) 다크 테마를 우선 사용하고, 패키지가 없으면
'clam' 기반 다크 팔레트로 대체한다. 위젯 생성 코드는 그대로 두고 스타일만 바꾼다.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

BG = "#1c1c1c"
SURFACE = "#262626"
SURFACE_2 = "#2f2f2f"
BORDER = "#3a3a3a"
TEXT = "#f2f2f2"
MUTED = "#9a9a9a"
ACCENT = "#d4a24c"        # 라크무 금빛
ACCENT_HOVER = "#e2b660"
ACCENT_TEXT = "#1a1406"
OK = "#6cc070"
FONT_FAMILY = "맑은 고딕"


def _pick_family(root):
    fams = set(tkfont.families(root))
    for f in ("맑은 고딕", "Malgun Gothic", "Segoe UI", "Noto Sans CJK KR", "DejaVu Sans"):
        if f in fams:
            return f
    return "TkDefaultFont"


def apply(root: tk.Tk) -> str:
    """root 에 테마를 적용하고 사용한 테마 이름을 돌려준다."""
    global FONT_FAMILY
    FONT_FAMILY = _pick_family(root)
    used = "clam"
    try:
        import sv_ttk  # type: ignore
        sv_ttk.set_theme("dark", root)
        used = "sun-valley-dark"
    except Exception:
        _clam_dark(root)

    for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont", "TkCaptionFont"):
        try:
            tkfont.nametofont(name).configure(family=FONT_FAMILY, size=10)
        except tk.TclError:
            pass

    st = ttk.Style(root)
    bg = st.lookup("TFrame", "background") or BG
    root.configure(background=bg)
    root.option_add("*Canvas.background", bg)
    root.option_add("*Canvas.highlightThickness", 0)
    root.option_add("*Text.background", SURFACE)
    root.option_add("*Text.foreground", TEXT)
    root.option_add("*Text.insertBackground", TEXT)
    root.option_add("*Text.relief", "flat")
    root.option_add("*Text.font", (FONT_FAMILY, 9))
    root.option_add("*Toplevel.background", bg)
    root.option_add("*Listbox.background", SURFACE)
    root.option_add("*Listbox.foreground", TEXT)

    st.configure("TNotebook.Tab", padding=(14, 6), font=(FONT_FAMILY, 10))
    st.configure("Header.TFrame", background=bg)
    st.configure("Header.TLabel", background=bg, foreground=TEXT)
    st.configure("Brand.TLabel", background=bg, foreground=ACCENT, font=(FONT_FAMILY, 22, "bold"))
    st.configure("Sub.TLabel", background=bg, foreground=MUTED, font=(FONT_FAMILY, 9))
    st.configure("Badge.TLabel", background=SURFACE_2, foreground=TEXT, font=(FONT_FAMILY, 9, "bold"),
                 padding=(10, 4))
    st.configure("Muted.TLabel", foreground=MUTED)
    st.configure("Title.TLabel", font=(FONT_FAMILY, 13, "bold"))
    st.configure("Footer.TFrame", background=bg)
    st.configure("Play.TButton", font=(FONT_FAMILY, 12, "bold"), padding=(18, 12))
    st.configure("PlayAlt.TButton", font=(FONT_FAMILY, 12, "bold"), padding=(18, 12))
    if used == "sun-valley-dark":
        # Accent.TButton 은 sv-ttk 제공. 크기만 키운다.
        st.configure("Accent.TButton", font=(FONT_FAMILY, 12, "bold"), padding=(18, 12))
    return used


def _clam_dark(root):
    st = ttk.Style(root)
    st.theme_use("clam")
    st.configure(".", background=BG, foreground=TEXT, fieldbackground=SURFACE_2,
                 bordercolor=BORDER, lightcolor=SURFACE, darkcolor=BG, troughcolor=SURFACE,
                 focuscolor=ACCENT, selectbackground=ACCENT, selectforeground=ACCENT_TEXT,
                 insertcolor=TEXT, font=(FONT_FAMILY, 10))
    st.map(".", foreground=[("disabled", "#666666")])
    st.configure("TFrame", background=BG)
    st.configure("TLabel", background=BG, foreground=TEXT)
    st.configure("TLabelframe", background=BG, bordercolor=BORDER, relief="solid")
    st.configure("TLabelframe.Label", background=BG, foreground=ACCENT, font=(FONT_FAMILY, 10, "bold"))
    st.configure("TButton", background=SURFACE_2, foreground=TEXT, bordercolor=BORDER,
                 padding=(10, 6), relief="flat")
    st.map("TButton", background=[("pressed", BORDER), ("active", "#383838")])
    st.configure("Accent.TButton", background=ACCENT, foreground=ACCENT_TEXT, bordercolor=ACCENT,
                 font=(FONT_FAMILY, 12, "bold"), padding=(18, 12))
    st.map("Accent.TButton", background=[("pressed", ACCENT), ("active", ACCENT_HOVER)])
    st.configure("TEntry", fieldbackground=SURFACE_2, foreground=TEXT, bordercolor=BORDER, padding=6)
    st.configure("TCombobox", fieldbackground=SURFACE_2, background=SURFACE_2, foreground=TEXT,
                 arrowcolor=TEXT, bordercolor=BORDER)
    st.configure("TCheckbutton", background=BG, foreground=TEXT, indicatorbackground=SURFACE_2)
    st.map("TCheckbutton", indicatorbackground=[("selected", ACCENT)])
    st.configure("TRadiobutton", background=BG, foreground=TEXT, indicatorbackground=SURFACE_2)
    st.configure("TNotebook", background=BG, bordercolor=BORDER, tabmargins=(0, 4, 0, 0))
    st.configure("TNotebook.Tab", background=SURFACE, foreground=MUTED, bordercolor=BORDER)
    st.map("TNotebook.Tab", background=[("selected", BG)], foreground=[("selected", ACCENT)])
    st.configure("Treeview", background=SURFACE, fieldbackground=SURFACE, foreground=TEXT,
                 bordercolor=BORDER, rowheight=24)
    st.configure("Treeview.Heading", background=SURFACE_2, foreground=TEXT, relief="flat")
    st.configure("Vertical.TScrollbar", background=SURFACE_2, troughcolor=BG, arrowcolor=MUTED,
                 bordercolor=BG)
