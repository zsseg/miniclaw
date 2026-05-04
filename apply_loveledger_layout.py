#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import ast
import re
from pathlib import Path


PROJECT_ROOT = Path.cwd()
WORKSPACE_APP = PROJECT_ROOT / "src" / "clawmini" / "workspace_app.py"


NEW_BUILD_UI = r"""
    def _build_ui(self) -> None:
        # LoveLedger 风格 QQ 自动回复控制台。
        for child in self.root_frame.winfo_children():
            child.destroy()

        self.root_frame.configure(style="Paper.TFrame")
        self.root_frame.grid_rowconfigure(0, weight=1)
        self.root_frame.grid_columnconfigure(0, weight=0, minsize=190)
        self.root_frame.grid_columnconfigure(1, weight=1, minsize=820)

        try:
            _style_text_widget = style_text_widget  # type: ignore[name-defined]
        except Exception:
            _style_text_widget = lambda widget: None
        try:
            _style_canvas = style_canvas  # type: ignore[name-defined]
        except Exception:
            _style_canvas = lambda canvas: None

        sidebar = tk.Frame(self.root_frame, bg="#285d52", width=190, highlightthickness=0, bd=0)
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_propagate(False)
        sidebar.grid_rowconfigure(10, weight=1)

        tk.Label(
            sidebar,
            text="⚓  ClawLedger",
            bg="#285d52",
            fg="#fff8e8",
            font=("Georgia", 16, "bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=18, pady=(22, 0))

        tk.Label(
            sidebar,
            text="EST 2024 · FAMILY · BOT",
            bg="#285d52",
            fg="#d9cdb6",
            font=("Georgia", 7, "bold"),
            anchor="w",
        ).grid(row=1, column=0, sticky="ew", padx=20, pady=(4, 26))

        def _nav_item(row: int, icon: str, title: str, subtitle: str, active: bool = False) -> None:
            bg = "#fff8e8" if active else "#285d52"
            fg = "#285d52" if active else "#fff8e8"
            sub_fg = "#8b6b63" if active else "#d9cdb6"
            bd = 1 if active else 0
            box = tk.Frame(
                sidebar,
                bg=bg,
                highlightbackground="#201b18" if active else "#285d52",
                highlightthickness=bd,
            )
            box.grid(row=row, column=0, sticky="ew", padx=12, pady=5)
            box.grid_columnconfigure(1, weight=1)
            tk.Label(box, text=icon, bg=bg, fg=fg, font=("Microsoft YaHei UI", 13)).grid(
                row=0, column=0, rowspan=2, sticky="n", padx=(10, 8), pady=9
            )
            tk.Label(box, text=title, bg=bg, fg=fg, font=("Georgia", 10, "bold"), anchor="w").grid(
                row=0, column=1, sticky="ew", pady=(8, 0)
            )
            tk.Label(box, text=subtitle, bg=bg, fg=sub_fg, font=("Microsoft YaHei UI", 7), anchor="w").grid(
                row=1, column=1, sticky="ew", pady=(0, 8)
            )

        _nav_item(2, "▦", "Overview", "Bot Dispatch", True)
        _nav_item(3, "✉", "Ledger", "Logs & Chat")
        _nav_item(4, "▣", "The Vault", "NapCat Setup")
        _nav_item(5, "✧", "Envelopes", "Groups & Rules")
        _nav_item(6, "☄", "Advisor", "Model Tips")

        signout = tk.Frame(sidebar, bg="#285d52", highlightbackground="#78a99d", highlightthickness=1)
        signout.grid(row=11, column=0, sticky="ew", padx=14, pady=(10, 22))
        tk.Label(
            signout,
            text="↪  STATUS DESK",
            bg="#285d52",
            fg="#fff8e8",
            font=("Georgia", 8, "bold"),
        ).pack(fill=tk.X, padx=10, pady=9)

        page = ttk.Frame(self.root_frame, style="Paper.TFrame")
        page.grid(row=0, column=1, sticky="nsew", padx=22, pady=18)
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(3, weight=1)

        header = ttk.Frame(page, style="Paper.TFrame")
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(0, weight=1)

        title_box = ttk.Frame(header, style="Paper.TFrame")
        title_box.grid(row=0, column=0, sticky="w")
        ttk.Label(title_box, text="QQ Bot Overview", style="Title.TLabel").pack(anchor=tk.W)
        ttk.Label(
            title_box,
            text="A vintage ledger-style control desk for your auto-reply cat.",
            style="Subtitle.TLabel",
        ).pack(anchor=tk.W, pady=(2, 0))

        top_actions = ttk.Frame(header, style="Paper.TFrame")
        top_actions.grid(row=0, column=1, sticky="e")
        ttk.Button(top_actions, text="🏛 VAULT", command=self.on_qq_status, style="Secondary.TButton").grid(
            row=0, column=0, padx=(0, 8)
        )
        ttk.Button(top_actions, text="+ LOG ENTRY", command=self.on_qq_configure, style="Primary.TButton").grid(
            row=0, column=1
        )

        metrics = ttk.Frame(page, style="Paper.TFrame")
        metrics.grid(row=1, column=0, sticky="ew", pady=(22, 14))
        for col in range(4):
            metrics.grid_columnconfigure(col, weight=1, uniform="metric")

        def _metric_card(parent: ttk.Frame, col: int, icon: str, label: str, value: str, hint: str, tag: str) -> None:
            card = tk.Frame(parent, bg="#fff8e8", highlightbackground="#221e1b", highlightthickness=1, bd=0)
            card.grid(row=0, column=col, sticky="ew", padx=(0 if col == 0 else 10, 0))
            card.grid_columnconfigure(1, weight=1)
            tk.Label(card, text=icon, bg="#fff8e8", fg="#285d52", font=("Microsoft YaHei UI", 16)).grid(
                row=0, column=0, rowspan=3, sticky="n", padx=(14, 10), pady=14
            )
            tk.Label(card, text=label, bg="#fff8e8", fg="#7e5850", font=("Georgia", 9, "bold"), anchor="w").grid(
                row=0, column=1, sticky="ew", pady=(12, 0)
            )
            tk.Label(card, text=value, bg="#fff8e8", fg="#26211f", font=("Georgia", 15, "bold"), anchor="w").grid(
                row=1, column=1, sticky="ew", pady=(5, 0)
            )
            tk.Label(card, text=hint, bg="#fff8e8", fg="#756c61", font=("Microsoft YaHei UI", 7), anchor="w").grid(
                row=2, column=1, sticky="ew", pady=(2, 12)
            )
            tk.Label(
                card,
                text=tag,
                bg="#285d52" if tag in {"ONLINE", "AUTO"} else "#b85757" if tag == "PAUSED" else "#747a91",
                fg="#fff8e8",
                font=("Georgia", 6, "bold"),
                padx=7,
                pady=2,
            ).place(relx=1.0, x=-10, y=8, anchor="ne")

        _metric_card(metrics, 0, "☷", "Auto Reply", "Enabled", "reply switch & private mode", "AUTO")
        _metric_card(metrics, 1, "↗", "Model", self.text_api_provider_var.get() or "deepseek", "text API provider", "CREDIT")
        _metric_card(metrics, 2, "↘", "Gateway", self.qq_gateway_var.get() or "managed", "NapCat / managed / mock", "ONLINE")
        _metric_card(metrics, 3, "▣", "Groups", self.qq_group_var.get() or "demo_chat", "target group ledger", "NET")

        dashboard = ttk.Frame(page, style="Paper.TFrame")
        dashboard.grid(row=2, column=0, sticky="nsew")
        dashboard.grid_columnconfigure(0, weight=3, minsize=520)
        dashboard.grid_columnconfigure(1, weight=1, minsize=270)
        dashboard.grid_rowconfigure(0, weight=1)

        log_card = ttk.LabelFrame(dashboard, text="Categorical Breakdown · Live Logs", padding=10, style="Card.TLabelframe")
        log_card.grid(row=0, column=0, sticky="nsew", padx=(0, 14))
        log_card.grid_rowconfigure(0, weight=1)
        log_card.grid_columnconfigure(0, weight=1)

        self.qq_chat_display = tk.Text(log_card, wrap=tk.WORD, state=tk.DISABLED, font=("Consolas", 10))
        self.qq_chat_display.grid(row=0, column=0, sticky="nsew")
        _style_text_widget(self.qq_chat_display)

        chat_scroll = ttk.Scrollbar(log_card, orient=tk.VERTICAL, command=self.qq_chat_display.yview)
        chat_scroll.grid(row=0, column=1, sticky="ns")
        self.qq_chat_display.configure(yscrollcommand=chat_scroll.set)

        self.qq_chat_display.tag_configure("msg_in", foreground="#285d52", font=("Microsoft YaHei UI", 10, "bold"))
        self.qq_chat_display.tag_configure("msg_out", foreground="#b85757", font=("Microsoft YaHei UI", 10, "bold"))
        self.qq_chat_display.tag_configure("msg_sys", foreground="#7b7167", font=("Microsoft YaHei UI", 9))

        side_cards = ttk.Frame(dashboard, style="Paper.TFrame")
        side_cards.grid(row=0, column=1, sticky="nsew")
        side_cards.grid_columnconfigure(0, weight=1)

        recent = tk.Frame(side_cards, bg="#26211f", highlightbackground="#221e1b", highlightthickness=1)
        recent.grid(row=0, column=0, sticky="ew")
        recent.grid_columnconfigure(0, weight=1)
        tk.Label(recent, text="RECENT STATUS", bg="#26211f", fg="#fff8e8", font=("Georgia", 10, "bold"), anchor="w").grid(
            row=0, column=0, sticky="ew", padx=12, pady=(12, 2)
        )
        tk.Label(recent, textvariable=self.qq_status_text, bg="#26211f", fg="#efe2cb", font=("Microsoft YaHei UI", 8), justify=tk.LEFT, wraplength=240, anchor="w").grid(
            row=1, column=0, sticky="ew", padx=12, pady=(6, 3)
        )
        tk.Label(recent, textvariable=self.qq_webhook_url_var, bg="#26211f", fg="#c9bda8", font=("Microsoft YaHei UI", 8), justify=tk.LEFT, wraplength=240, anchor="w").grid(
            row=2, column=0, sticky="ew", padx=12, pady=(3, 12)
        )

        actions = ttk.LabelFrame(side_cards, text="Vault Actions", padding=10, style="Card.TLabelframe")
        actions.grid(row=1, column=0, sticky="ew", pady=(14, 0))
        for i in range(2):
            actions.grid_columnconfigure(i, weight=1)

        ttk.Button(actions, text="下载NapCat", command=self.on_qq_download_napcat, style="Secondary.TButton").grid(row=0, column=0, sticky="ew", padx=(0, 6), pady=4)
        ttk.Button(actions, text="一键启动/填充", command=self.on_qq_bootstrap, style="Primary.TButton").grid(row=0, column=1, sticky="ew", pady=4)
        ttk.Button(actions, text="更新配置", command=self.on_qq_configure, style="Success.TButton").grid(row=1, column=0, sticky="ew", padx=(0, 6), pady=4)
        ttk.Button(actions, text="查询状态", command=self.on_qq_status, style="Secondary.TButton").grid(row=1, column=1, sticky="ew", pady=4)
        ttk.Button(actions, text="轮询待回复", command=self.on_qq_poll_pending, style="Secondary.TButton").grid(row=2, column=0, sticky="ew", padx=(0, 6), pady=4)
        ttk.Button(actions, text="绑定客户端", command=self.on_qq_bind_local_client_auto, style="Secondary.TButton").grid(row=2, column=1, sticky="ew", pady=4)
        ttk.Button(actions, text="暂停", command=self.on_qq_pause, style="Warning.TButton").grid(row=3, column=0, sticky="ew", padx=(0, 6), pady=4)
        ttk.Button(actions, text="恢复", command=self.on_qq_resume, style="Success.TButton").grid(row=3, column=1, sticky="ew", pady=4)
        ttk.Button(actions, text="重启事件服务器", command=self.on_qq_restart_webhook, style="Danger.TButton").grid(row=4, column=0, columnspan=2, sticky="ew", pady=(8, 4))

        cfg_shell = ttk.LabelFrame(page, text="Ledger Configuration", padding=10, style="Card.TLabelframe")
        cfg_shell.grid(row=3, column=0, sticky="nsew", pady=(16, 0))
        cfg_shell.grid_rowconfigure(0, weight=1)
        cfg_shell.grid_columnconfigure(0, weight=1)

        config_canvas = tk.Canvas(cfg_shell, highlightthickness=0, height=260)
        _style_canvas(config_canvas)
        config_scroll = ttk.Scrollbar(cfg_shell, orient=tk.VERTICAL, command=config_canvas.yview)
        body = ttk.Frame(config_canvas, style="Surface.TFrame")
        body_window = config_canvas.create_window((0, 0), window=body, anchor="nw")

        def _sync_config_scroll(_event: tk.Event[Any] = None) -> None:
            config_canvas.configure(scrollregion=config_canvas.bbox("all"))

        def _sync_config_width(event: tk.Event[Any]) -> None:
            config_canvas.itemconfig(body_window, width=event.width)

        body.bind("<Configure>", _sync_config_scroll)
        config_canvas.bind("<Configure>", _sync_config_width)
        config_canvas.configure(yscrollcommand=config_scroll.set)
        config_canvas.grid(row=0, column=0, sticky="nsew")
        config_scroll.grid(row=0, column=1, sticky="ns")

        def _on_cfg_mousewheel(event: tk.Event[Any]) -> None:
            config_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        config_canvas.bind("<Enter>", lambda _e: config_canvas.bind_all("<MouseWheel>", _on_cfg_mousewheel, add="+"))
        config_canvas.bind("<Leave>", lambda _e: config_canvas.unbind_all("<MouseWheel>"))

        api_box = ttk.LabelFrame(body, text="Text API · Model", padding=10, style="Card.TLabelframe")
        api_box.pack(fill=tk.X, padx=2, pady=(2, 10))
        for col in range(4):
            api_box.grid_columnconfigure(col, weight=1)

        ttk.Label(api_box, text="Provider").grid(row=0, column=0, sticky=tk.W)
        ttk.Combobox(api_box, textvariable=self.text_api_provider_var, values=["openai", "deepseek", "qwen", "mock"], width=12, state="readonly").grid(row=0, column=1, sticky="ew", padx=(8, 14))
        ttk.Label(api_box, text="Model").grid(row=0, column=2, sticky=tk.W)
        ttk.Entry(api_box, textvariable=self.text_api_model_var, width=20).grid(row=0, column=3, sticky="ew", padx=(8, 0))

        ttk.Label(api_box, text="API Key").grid(row=1, column=0, sticky=tk.W, pady=(8, 0))
        ttk.Entry(api_box, textvariable=self.text_api_key_var, width=28, show="•").grid(row=1, column=1, sticky="ew", padx=(8, 14), pady=(8, 0))
        ttk.Label(api_box, text="Base URL").grid(row=1, column=2, sticky=tk.W, pady=(8, 0))
        ttk.Entry(api_box, textvariable=self.text_api_base_url_var, width=30).grid(row=1, column=3, sticky="ew", padx=(8, 0), pady=(8, 0))

        self.search_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(api_box, text="联网搜索（DeepSeek / Qwen 可用）", variable=self.search_var).grid(
            row=2, column=0, columnspan=4, sticky=tk.W, pady=(10, 0)
        )

        cfg = ttk.LabelFrame(body, text="Auto Reply Rules", padding=10, style="Card.TLabelframe")
        cfg.pack(fill=tk.X, padx=2, pady=(0, 10))
        for col in range(7):
            cfg.grid_columnconfigure(col, weight=1)

        ttk.Label(cfg, text="目标群号").grid(row=0, column=0, sticky=tk.W)
        ttk.Entry(cfg, textvariable=self.qq_group_var, width=26).grid(row=0, column=1, columnspan=2, sticky="ew", padx=(8, 14))
        ttk.Label(cfg, text="私聊延时").grid(row=0, column=3, sticky=tk.W)
        ttk.Entry(cfg, textvariable=self.qq_delay_var, width=8).grid(row=0, column=4, sticky=tk.W, padx=(8, 12))
        ttk.Label(cfg, text="冷却").grid(row=0, column=5, sticky=tk.W)
        ttk.Entry(cfg, textvariable=self.qq_cooldown_var, width=8).grid(row=0, column=6, sticky=tk.W, padx=(8, 0))

        ttk.Label(cfg, text="当前账号ID").grid(row=1, column=0, sticky=tk.W, pady=(8, 0))
        ttk.Entry(cfg, textvariable=self.qq_self_user_var, width=16).grid(row=1, column=1, sticky="ew", padx=(8, 14), pady=(8, 0))
        ttk.Checkbutton(cfg, text="启用私聊回复", variable=self.qq_private_enabled_var).grid(row=1, column=2, sticky=tk.W, pady=(8, 0))
        ttk.Checkbutton(cfg, text="启用自动回复", variable=self.qq_enabled_var).grid(row=1, column=3, sticky=tk.W, pady=(8, 0))
        ttk.Label(cfg, text="网关").grid(row=1, column=4, sticky=tk.W, pady=(8, 0))
        ttk.Combobox(cfg, textvariable=self.qq_gateway_var, values=["mock", "managed", "windows"], width=10, state="readonly").grid(row=1, column=5, columnspan=2, sticky="ew", padx=(8, 0), pady=(8, 0))

        ttk.Checkbutton(cfg, text="连接后立即尝试发送", variable=self.qq_connect_now_var).grid(row=2, column=0, columnspan=2, sticky=tk.W, pady=(8, 0))
        ttk.Checkbutton(cfg, text="图片识别", variable=self.qq_image_recognition_var).grid(row=2, column=2, sticky=tk.W, pady=(8, 0))

        ttk.Label(cfg, text="群号管理").grid(row=3, column=0, sticky=tk.W, pady=(10, 0))
        ttk.Entry(cfg, textvariable=self.qq_group_edit_var, width=14).grid(row=3, column=1, sticky="ew", padx=(8, 8), pady=(10, 0))
        ttk.Button(cfg, text="新增", command=self.on_qq_group_add, style="Secondary.TButton").grid(row=3, column=2, sticky="ew", padx=(0, 8), pady=(10, 0))
        ttk.Button(cfg, text="删除", command=self.on_qq_group_remove, style="Secondary.TButton").grid(row=3, column=3, sticky="ew", padx=(0, 8), pady=(10, 0))
        ttk.Label(cfg, text="新群号").grid(row=3, column=4, sticky=tk.W, pady=(10, 0))
        ttk.Entry(cfg, textvariable=self.qq_group_new_var, width=14).grid(row=3, column=5, sticky="ew", padx=(8, 8), pady=(10, 0))
        ttk.Button(cfg, text="修改", command=self.on_qq_group_update, style="Secondary.TButton").grid(row=3, column=6, sticky="ew", pady=(10, 0))

        ttk.Label(cfg, text="猫娘提示词").grid(row=4, column=0, sticky=tk.W, pady=(10, 0))
        ttk.Entry(cfg, textvariable=self.qq_prompt_var).grid(row=4, column=1, columnspan=6, sticky="ew", padx=(8, 0), pady=(10, 0))

        managed = ttk.LabelFrame(body, text="NapCat · Managed Gateway", padding=10, style="Card.TLabelframe")
        managed.pack(fill=tk.X, padx=2, pady=(0, 10))
        for col in range(4):
            managed.grid_columnconfigure(col, weight=1)

        ttk.Label(managed, text="API 基址").grid(row=0, column=0, sticky=tk.W)
        ttk.Entry(managed, textvariable=self.qq_managed_api_base_var).grid(row=0, column=1, columnspan=3, sticky="ew", padx=(8, 0))
        ttk.Label(managed, text="发送 Token").grid(row=1, column=0, sticky=tk.W, pady=(8, 0))
        ttk.Entry(managed, textvariable=self.qq_managed_token_var, show="•").grid(row=1, column=1, sticky="ew", padx=(8, 14), pady=(8, 0))
        ttk.Label(managed, text="接收 Token").grid(row=1, column=2, sticky=tk.W, pady=(8, 0))
        ttk.Entry(managed, textvariable=self.qq_receive_token_var, show="•").grid(row=1, column=3, sticky="ew", padx=(8, 0), pady=(8, 0))
        ttk.Label(managed, text="账号 ID").grid(row=2, column=0, sticky=tk.W, pady=(8, 0))
        ttk.Entry(managed, textvariable=self.qq_managed_account_var, width=16).grid(row=2, column=1, sticky="ew", padx=(8, 14), pady=(8, 0))
        ttk.Label(
            managed,
            text="发送 Token 用于 MiniClaw 调 NapCat 发消息；接收 Token 用于校验 NapCat 事件上报。",
            style="Muted.TLabel",
        ).grid(row=3, column=0, columnspan=4, sticky=tk.W, pady=(8, 0))

        simulate = ttk.LabelFrame(body, text="Simulation · Dry Run", padding=10, style="Card.TLabelframe")
        simulate.pack(fill=tk.X, padx=2, pady=(0, 2))
        for col in range(6):
            simulate.grid_columnconfigure(col, weight=1)

        ttk.Label(simulate, text="消息来源").grid(row=0, column=0, sticky=tk.W)
        ttk.Combobox(simulate, textvariable=self.qq_source_var, values=["private", "group"], width=10, state="readonly").grid(row=0, column=1, sticky="ew", padx=(8, 12))
        ttk.Label(simulate, text="会话ID").grid(row=0, column=2, sticky=tk.W)
        ttk.Entry(simulate, textvariable=self.qq_chat_var, width=18).grid(row=0, column=3, sticky="ew", padx=(8, 12))
        ttk.Button(simulate, text="模拟收到消息", command=self.on_qq_simulate_message, style="Primary.TButton").grid(row=0, column=4, sticky="ew", padx=(0, 8))
        ttk.Button(simulate, text="模拟手动回复", command=self.on_qq_manual_replied, style="Secondary.TButton").grid(row=0, column=5, sticky="ew")

        ttk.Label(simulate, text="发送者ID").grid(row=1, column=0, sticky=tk.W, pady=(8, 0))
        ttk.Entry(simulate, textvariable=self.qq_sender_var, width=16).grid(row=1, column=1, sticky="ew", padx=(8, 12), pady=(8, 0))
        ttk.Label(simulate, text="已等待").grid(row=1, column=2, sticky=tk.W, pady=(8, 0))
        ttk.Entry(simulate, textvariable=self.qq_waited_sec_var, width=8).grid(row=1, column=3, sticky=tk.W, padx=(8, 12), pady=(8, 0))
        ttk.Label(simulate, text="消息内容").grid(row=2, column=0, sticky=tk.W, pady=(8, 0))
        ttk.Entry(simulate, textvariable=self.qq_text_var).grid(row=2, column=1, columnspan=5, sticky="ew", padx=(8, 0), pady=(8, 0))
"""


def find_method_range(src: str, class_name: str, method_name: str) -> tuple[int, int]:
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == method_name:
                    if item.end_lineno is None:
                        raise RuntimeError("当前 Python AST 没有 end_lineno，无法安全替换。")
                    return item.lineno, item.end_lineno
    raise RuntimeError(f"找不到 {class_name}.{method_name}")


def main() -> None:
    if not WORKSPACE_APP.exists():
        raise SystemExit(f"找不到文件：{WORKSPACE_APP}")

    src = WORKSPACE_APP.read_text(encoding="utf-8")
    backup = WORKSPACE_APP.with_suffix(".py.bak_loveledger")
    backup.write_text(src, encoding="utf-8")

    if "from clawmini.ui_theme import apply_theme" in src and "style_text_widget" not in src:
        src = src.replace(
            "from clawmini.ui_theme import apply_theme",
            "from clawmini.ui_theme import apply_theme, style_text_widget, style_canvas",
        )
    elif "from clawmini.ui_theme import apply_theme" not in src:
        src = re.sub(
            r"(from tkinter import[^\n]+\n)",
            r"\1from clawmini.ui_theme import apply_theme, style_text_widget, style_canvas\n",
            src,
            count=1,
        )

    src = src.replace(
        'self.qq_status_text.set(f"轮询待回复: {result.output.strip()[:80]}")',
        'self.qq_panel.qq_status_text.set(f"轮询待回复: {result.output.strip()[:80]}")',
    )

    start, end = find_method_range(src, "QQAutoReplyPanel", "_build_ui")
    lines = src.splitlines()
    new_lines = lines[: start - 1] + NEW_BUILD_UI.strip("\n").splitlines() + lines[end:]
    src2 = "\n".join(new_lines) + "\n"

    compile(src2, str(WORKSPACE_APP), "exec")
    WORKSPACE_APP.write_text(src2, encoding="utf-8")

    print("✅ 已完成 LoveLedger 布局改造")
    print(f"备份文件：{backup}")
    print("下一步运行：")
    print("  python -m py_compile .\\src\\clawmini\\workspace_app.py")
    print("  python app.py")


if __name__ == "__main__":
    main()
