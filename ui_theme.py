"""런처 UI 테마.

Sun Valley(sv-ttk, Windows 11 스타일) 다크 테마를 쓰되 글꼴은 전부 한 가지 한글 글꼴
(맑은 고딕)과 한 가지 크기 체계로 통일한다. sv-ttk 기본 글꼴(Segoe UI Variable)에는
한글이 없어 Windows 가 위젯마다 다른 대체 글꼴을 쓰므로 반드시 덮어쓴다.
패키지가 없으면 'clam' 기반 다크 팔레트로 대체한다.
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
ACCENT = "#d4a24c"
ACCENT_HOVER = "#e2b660"
ACCENT_TEXT = "#1a1406"
FONT_FAMILY = "맑은 고딕"

# 크기 체계 (pt): 본문 10, 보조 9, 소제목 10 굵게, 제목 13 굵게, 실행 버튼 12 굵게, 로고 22 굵게
SIZE_CAPTION = 9
SIZE_BODY = 10
SIZE_TITLE = 13
SIZE_BUTTON_LARGE = 12
SIZE_BRAND = 22

_NAMED = {
    # Tk 기본 글꼴
    "TkDefaultFont": (SIZE_BODY, "normal"),
    "TkTextFont": (SIZE_BODY, "normal"),
    "TkMenuFont": (SIZE_BODY, "normal"),
    "TkHeadingFont": (SIZE_BODY, "bold"),
    "TkCaptionFont": (SIZE_BODY, "bold"),
    "TkSmallCaptionFont": (SIZE_CAPTION, "normal"),
    "TkTooltipFont": (SIZE_CAPTION, "normal"),
    "TkIconFont": (SIZE_BODY, "normal"),
    "TkFixedFont": (SIZE_BODY, "normal"),
    # sv-ttk 글꼴 (Segoe UI Variable -> 맑은 고딕)
    "SunValleyCaptionFont": (SIZE_CAPTION, "bold"),
    "SunValleyBodyFont": (SIZE_BODY, "normal"),
    "SunValleyBodyStrongFont": (SIZE_BODY, "bold"),
    "SunValleyBodyLargeFont": (SIZE_BUTTON_LARGE, "normal"),
    "SunValleySubtitleFont": (SIZE_TITLE, "bold"),
    "SunValleyTitleFont": (SIZE_TITLE + 3, "bold"),
    "SunValleyTitleLargeFont": (SIZE_BRAND, "bold"),
    "SunValleyDisplayFont": (SIZE_BRAND + 6, "bold"),
}


def _pick_family(root):
    fams = set(tkfont.families(root))
    for f in ("맑은 고딕", "Malgun Gothic", "Noto Sans KR", "Noto Sans CJK KR", "NanumGothic", "Segoe UI"):
        if f in fams:
            return f
    return "TkDefaultFont"


def font(size=SIZE_BODY, weight="normal"):
    return (FONT_FAMILY, size, weight)


def _unify_fonts(root):
    for name, (size, weight) in _NAMED.items():
        try:
            tkfont.nametofont(name, root=root).configure(family=FONT_FAMILY, size=size, weight=weight)
        except tk.TclError:
            pass  # 해당 테마/플랫폼에 없는 글꼴 이름


def apply(root: tk.Tk) -> str:
    """root 에 테마를 적용하고 사용한 테마 이름을 돌려준다."""
    global FONT_FAMILY
    FONT_FAMILY = _pick_family(root)
    used = "clam"
    try:
        import sv_ttk  # type: ignore
        sv_ttk.set_theme("dark", root)
        used = "sun-valley-dark"
        # sv-ttk 는 <<ThemeChanged>> 때 색·글꼴을 다시 설정하고 tk_setPalette 로 옵션 DB 에
        # *foreground/*background 를 넣는다. 이 값이 ttk 라벨의 위젯 옵션이 되어 스타일 색을
        # 덮으므로, 이벤트를 먼저 처리시킨 뒤 옵션 DB 를 비우고 필요한 것만 다시 넣는다.
        # 기본 색은 지금 직접 적용하고, 스타일을 바꿀 때마다 다시 실행되는 루트 바인딩은 해제한다.
        root.tk.call("configure_colors")
        root.tk.eval("bind [winfo class .] <<ThemeChanged>> {}")
        root.update_idletasks()
        root.option_clear()
    except Exception:
        _clam_dark(root)
    _unify_fonts(root)

    st = ttk.Style(root)
    bg = st.lookup("TFrame", "background") or BG
    root.configure(background=bg)
    root.option_add("*Canvas.background", bg)
    root.option_add("*Canvas.highlightThickness", 0)
    root.option_add("*Text.background", SURFACE)
    root.option_add("*Text.foreground", TEXT)
    root.option_add("*Text.insertBackground", TEXT)
    root.option_add("*Text.relief", "flat")
    root.option_add("*Text.borderWidth", 0)
    root.option_add("*Text.highlightThickness", 1)
    root.option_add("*Text.highlightBackground", BORDER)
    root.option_add("*Text.highlightColor", BORDER)
    root.option_add("*Text.padX", 8)
    root.option_add("*Text.padY", 6)
    root.option_add("*Toplevel.background", bg)
    root.option_add("*Listbox.background", SURFACE)
    root.option_add("*Listbox.foreground", TEXT)

    # 모든 ttk 위젯을 같은 본문 글꼴로 (sv-ttk 가 위젯별로 지정한 글꼴까지 덮어씀)
    body = font()
    for sty in (".", "TLabel", "TButton", "TCheckbutton", "TRadiobutton", "TEntry", "TCombobox",
                "TSpinbox", "TMenubutton", "Treeview", "TNotebook.Tab", "Toolbutton", "Switch.TCheckbutton"):
        st.configure(sty, font=body)
    st.configure("TLabelframe.Label", font=font(SIZE_BODY, "bold"), foreground=ACCENT)
    st.configure("Treeview.Heading", font=font(SIZE_BODY, "bold"))
    st.configure("TNotebook.Tab", padding=(14, 6))

    st.configure("Body.TLabel", font=body)
    st.configure("Muted.TLabel", font=font(SIZE_CAPTION), foreground=MUTED)
    st.configure("Title.TLabel", font=font(SIZE_TITLE, "bold"))
    st.configure("Header.TFrame", background=bg)
    st.configure("Header.TLabel", background=bg, foreground=TEXT, font=body)
    st.configure("Brand.TLabel", background=bg, foreground=ACCENT, font=font(SIZE_BRAND, "bold"))
    st.configure("Sub.TLabel", background=bg, foreground=MUTED, font=font(SIZE_CAPTION))
    st.configure("Badge.TLabel", background=SURFACE_2, foreground=TEXT, font=font(SIZE_CAPTION, "bold"),
                 padding=(10, 4))
    st.configure("Footer.TFrame", background=bg)
    st.configure("Accent.TButton", font=font(SIZE_BUTTON_LARGE, "bold"), padding=(18, 10))
    return used


def _clam_dark(root):
    st = ttk.Style(root)
    st.theme_use("clam")
    st.configure(".", background=BG, foreground=TEXT, fieldbackground=SURFACE_2,
                 bordercolor=BORDER, lightcolor=SURFACE, darkcolor=BG, troughcolor=SURFACE,
                 focuscolor=ACCENT, selectbackground=ACCENT, selectforeground=ACCENT_TEXT,
                 insertcolor=TEXT)
    st.map(".", foreground=[("disabled", "#666666")])
    st.configure("TFrame", background=BG)
    st.configure("TLabel", background=BG, foreground=TEXT)
    st.configure("TLabelframe", background=BG, bordercolor=BORDER, relief="solid")
    st.configure("TLabelframe.Label", background=BG)
    st.configure("TButton", background=SURFACE_2, foreground=TEXT, bordercolor=BORDER,
                 padding=(10, 6), relief="flat")
    st.map("TButton", background=[("pressed", BORDER), ("active", "#383838")])
    st.configure("Accent.TButton", background=ACCENT, foreground=ACCENT_TEXT, bordercolor=ACCENT)
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
