"""LoveLedger 风格 UI 主题。"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk


PALETTE = {
    "paper": "#f3eee3",
    "paper_2": "#eee6d8",
    "card": "#fff8e8",
    "ink": "#26211f",
    "muted": "#7b7167",
    "green": "#285d52",
    "green_light": "#d9e7de",
    "red": "#b85757",
    "gold": "#d49b54",
    "border": "#27211d",
}

FONT_UI = ("Microsoft YaHei UI", 10)
FONT_UI_BOLD = ("Microsoft YaHei UI", 10, "bold")
FONT_TITLE = ("Georgia", 18, "bold")
FONT_SUBTITLE = ("Georgia", 10, "italic")
FONT_MONO = ("Consolas", 10)


def _safe_configure(style: ttk.Style, name: str, **kwargs) -> None:
    try:
        style.configure(name, **kwargs)
    except Exception:
        pass


def _safe_map(style: ttk.Style, name: str, **kwargs) -> None:
    try:
        style.map(name, **kwargs)
    except Exception:
        pass


def apply_theme(root: tk.Tk) -> None:
    style = ttk.Style(root)

    try:
        if "clam" in style.theme_names():
            style.theme_use("clam")
    except Exception:
        pass

    try:
        root.option_add("*Font", FONT_UI)
        root.option_add("*Background", PALETTE["paper"])
        root.option_add("*Foreground", PALETTE["ink"])
        root.configure(background=PALETTE["paper"])
    except Exception:
        pass

    _safe_configure(style, ".", background=PALETTE["paper"], foreground=PALETTE["ink"], font=FONT_UI)
    _safe_configure(style, "TFrame", background=PALETTE["paper"])
    _safe_configure(style, "Paper.TFrame", background=PALETTE["paper"])
    _safe_configure(style, "Surface.TFrame", background=PALETTE["card"])
    _safe_configure(style, "Card.TFrame", background=PALETTE["card"], relief="solid", borderwidth=1)

    _safe_configure(style, "TLabel", background=PALETTE["paper"], foreground=PALETTE["ink"], font=FONT_UI)
    _safe_configure(style, "Title.TLabel", background=PALETTE["paper"], foreground=PALETTE["ink"], font=FONT_TITLE)
    _safe_configure(style, "Hero.TLabel", background=PALETTE["paper"], foreground=PALETTE["ink"], font=FONT_TITLE)
    _safe_configure(style, "Subtitle.TLabel", background=PALETTE["paper"], foreground=PALETTE["muted"], font=FONT_SUBTITLE)
    _safe_configure(style, "Header.TLabel", background=PALETTE["paper"], foreground=PALETTE["ink"], font=("Georgia", 12, "bold"))
    _safe_configure(style, "Muted.TLabel", background=PALETTE["paper"], foreground=PALETTE["muted"], font=("Microsoft YaHei UI", 9))

    _safe_configure(style, "TLabelframe", background=PALETTE["card"], foreground=PALETTE["ink"], relief="solid", borderwidth=1, padding=10)
    _safe_configure(style, "TLabelframe.Label", background=PALETTE["paper"], foreground=PALETTE["ink"], font=("Georgia", 11, "bold"))
    _safe_configure(style, "Card.TLabelframe", background=PALETTE["card"], foreground=PALETTE["ink"], relief="solid", borderwidth=1, padding=10)
    _safe_configure(style, "Card.TLabelframe.Label", background=PALETTE["card"], foreground=PALETTE["ink"], font=("Georgia", 11, "bold"))

    _safe_configure(style, "TButton", padding=(12, 7), relief="solid", borderwidth=1, background=PALETTE["card"], foreground=PALETTE["ink"], font=FONT_UI_BOLD)
    _safe_map(style, "TButton", background=[("active", PALETTE["paper_2"]), ("pressed", "#e6d8c7")])

    _safe_configure(style, "Primary.TButton", padding=(13, 8), relief="solid", borderwidth=1, background=PALETTE["ink"], foreground=PALETTE["card"], font=FONT_UI_BOLD)
    _safe_map(style, "Primary.TButton", background=[("active", "#3a3430"), ("pressed", "#11100f")])

    _safe_configure(style, "Secondary.TButton", padding=(12, 7), relief="solid", borderwidth=1, background=PALETTE["card"], foreground=PALETTE["ink"], font=FONT_UI_BOLD)
    _safe_configure(style, "Success.TButton", background=PALETTE["green"], foreground=PALETTE["card"], padding=(12, 7), relief="solid")
    _safe_configure(style, "Warning.TButton", background=PALETTE["gold"], foreground=PALETTE["ink"], padding=(12, 7), relief="solid")
    _safe_configure(style, "Danger.TButton", background=PALETTE["red"], foreground=PALETTE["card"], padding=(12, 7), relief="solid")

    for stylename in ("TEntry", "TSpinbox"):
        _safe_configure(style, stylename, fieldbackground=PALETTE["card"], background=PALETTE["card"], foreground=PALETTE["ink"], insertcolor=PALETTE["ink"], padding=5, relief="solid", borderwidth=1)

    _safe_configure(style, "TCombobox", fieldbackground=PALETTE["card"], background=PALETTE["card"], foreground=PALETTE["ink"], arrowcolor=PALETTE["ink"], padding=5, relief="solid", borderwidth=1)
    _safe_map(style, "TCombobox", fieldbackground=[("readonly", PALETTE["card"])], background=[("active", PALETTE["paper_2"])])

    _safe_configure(style, "TNotebook", background=PALETTE["paper"], borderwidth=0)
    _safe_configure(style, "TNotebook.Tab", padding=(14, 9), background=PALETTE["paper_2"], foreground=PALETTE["ink"], font=FONT_UI_BOLD)
    _safe_map(style, "TNotebook.Tab", background=[("selected", PALETTE["card"]), ("active", "#eadfcc")])

    _safe_configure(style, "Vertical.TScrollbar", background=PALETTE["paper_2"], troughcolor=PALETTE["card"], arrowcolor=PALETTE["ink"])
    _safe_configure(style, "Horizontal.TScrollbar", background=PALETTE["paper_2"], troughcolor=PALETTE["card"], arrowcolor=PALETTE["ink"])
    _safe_configure(style, "TCheckbutton", background=PALETTE["paper"], foreground=PALETTE["ink"], font=FONT_UI)
    _safe_configure(style, "TRadiobutton", background=PALETTE["paper"], foreground=PALETTE["ink"], font=FONT_UI)

    try:
        root.option_add("*Text.Background", PALETTE["card"])
        root.option_add("*Text.Foreground", PALETTE["ink"])
        root.option_add("*Text.InsertBackground", PALETTE["ink"])
        root.option_add("*Text.SelectBackground", PALETTE["green_light"])
        root.option_add("*Text.SelectForeground", PALETTE["ink"])
        root.option_add("*Text.Font", FONT_MONO)
        root.option_add("*Listbox.Background", PALETTE["card"])
        root.option_add("*Listbox.Foreground", PALETTE["ink"])
        root.option_add("*Listbox.SelectBackground", PALETTE["green"])
        root.option_add("*Listbox.SelectForeground", PALETTE["card"])
    except Exception:
        pass


def style_text_widget(widget: tk.Text | tk.Widget) -> None:
    try:
        widget.configure(background=PALETTE["card"], foreground=PALETTE["ink"], insertbackground=PALETTE["ink"], selectbackground=PALETTE["green_light"], selectforeground=PALETTE["ink"], relief=tk.SOLID, borderwidth=1, highlightthickness=1, highlightbackground=PALETTE["border"], highlightcolor=PALETTE["green"], font=FONT_MONO, padx=10, pady=8)
    except Exception:
        pass


def style_canvas(canvas: tk.Canvas) -> None:
    try:
        canvas.configure(background=PALETTE["paper"], highlightthickness=0, borderwidth=0)
    except Exception:
        pass
