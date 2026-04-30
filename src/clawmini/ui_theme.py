"""UI 主题与样式辅助。

提供 `apply_theme(root)` 在应用启动时统一设置 ttk 样式和默认字体/配色。
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk


def apply_theme(root: tk.Tk) -> None:
    """为传入的 Tk 根窗口应用统一主题样式。

    采用可用的 ttk 主题（优先 'clam'），设置全局字体、配色与常见控件样式。
    该实现尽量保持兼容性，若运行平台/主题不完全支持某些属性会安静失败。
    """
    style = ttk.Style(root)
    try:
        themes = style.theme_names()
        if "clam" in themes:
            style.theme_use("clam")
        else:
            style.theme_use(themes[0])
    except Exception:
        # 主题选择不是关键，继续使用当前主题
        pass

    # 青蓝风格配色（简洁、柔和）
    # 青蓝风格配色（降低对比度，避免刺眼）
    palette = {
        "bg": "#eaf5f3",
        "surface": "#ffffff",
        "primary": "#47aeab",
        "primary_dark": "#3a9b98",
        "muted": "#7a8a8e",
        "text": "#063040",
        "muted_bg": "#d4edeb",
    }

    default_font = ("Microsoft YaHei UI", 11)

    # 全局默认字体与根背景
    try:
        root.option_add("*Font", default_font)
        root.configure(background=palette["bg"])
    except Exception:
        pass

    # 基本 ttk 控件样式（保持简洁、留白充足）
    style.configure(".", background=palette["bg"], foreground=palette["text"], font=default_font)
    style.configure("TFrame", background=palette["bg"])
    style.configure("Card.TFrame", background=palette["surface"], relief="flat", borderwidth=0)
    style.configure("TLabel", background=palette["bg"], foreground=palette["text"])
    style.configure(
        "Header.TLabel",
        background=palette["bg"],
        foreground=palette["text"],
        font=(default_font[0], 13, "bold"),
    )

    # 按钮：扁平+主色强调
    style.configure(
        "TButton",
        padding=8,
        relief="flat",
        background=palette["primary"],
        foreground="white",
        borderwidth=0,
    )
    style.map(
        "TButton",
        background=[("pressed", palette["primary_dark"]), ("active", palette["primary_dark"]), ("disabled", "#c0d6d4")],
        foreground=[("disabled", "#aec0c2")],
    )

    # 提供一个显式的主按钮样式，方便未来局部使用
    style.configure("Primary.TButton", foreground="white", background=palette["primary"], padding=8)

    style.configure(
        "TEntry",
        fieldbackground=palette["surface"],
        background=palette["surface"],
        foreground=palette["text"],
    )
    style.configure(
        "TCombobox",
        fieldbackground=palette["surface"],
        background=palette["surface"],
        foreground=palette["text"],
    )

    # Notebook（选项卡）风格：默认柔和背景，选中时为白卡片
    style.configure("TNotebook", background=palette["bg"], borderwidth=0)
    style.configure(
        "TNotebook.Tab",
        padding=[12, 8],
        background=palette["muted_bg"],
        foreground=palette["text"],
        font=(default_font[0], 10),
    )
    style.map("TNotebook.Tab", background=[("selected", palette["surface"])])

    # LabelFrame / Card 风格，适合作为信息卡片
    style.configure("Card.TLabelframe", background=palette["surface"], foreground=palette["text"])
    style.configure("Card.TLabelframe.Label", background=palette["surface"], foreground=palette["text"]) 

    # 文本类 Widget 的默认设置（编辑区、控制台）
    try:
        root.option_add("*Text.Background", palette["surface"])
        root.option_add("*Text.Foreground", palette["text"])
        root.option_add("*Text.Font", ("Consolas", 11))
        root.option_add("*Entry.Background", palette["surface"])
    except Exception:
        pass

    # 小调整，尽量减少控件边框视觉噪音
    try:
        style.configure("Toolbutton", relief="flat")
    except Exception:
        pass

    # 额外美化：次级、轮廓按钮与输入框聚焦样式
    try:
        style.configure(
            "Secondary.TButton",
            padding=8,
            relief="flat",
            background=palette["muted_bg"],
            foreground=palette["text"],
            borderwidth=0,
        )
        style.map(
            "Secondary.TButton",
            background=[("active", palette["surface"])],
            foreground=[("disabled", "#aec0c2")],
        )

        style.configure(
            "Outline.TButton",
            padding=6,
            relief="flat",
            background=palette["bg"],
            foreground=palette["primary"],
            borderwidth=1,
        )
        style.map(
            "Outline.TButton",
            background=[("active", palette["muted_bg"])],
            foreground=[("active", palette["primary_dark"])],
        )

        # 输入框 focus 高亮（在支持的主题下生效）
        style.map("TEntry", fieldbackground=[("focus", palette["surface"])])
        style.map("TEntry", foreground=[("disabled", "#aec0c2")])

        # 下拉在焦点时使用白色卡片背景以突出
        style.map("TCombobox", fieldbackground=[("focus", palette["surface"])])
    except Exception:
        pass

    # 尝试使用 ttk 内置圆角样式（部分主题支持 'rounded' 子样式）
    try:
        style.configure("TRadiobutton", relief="flat")
    except Exception:
        pass
