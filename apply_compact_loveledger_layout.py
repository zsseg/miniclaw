#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import ast
from pathlib import Path


PROJECT_ROOT = Path.cwd()
WORKSPACE_APP = PROJECT_ROOT / "src" / "clawmini" / "workspace_app.py"


NEW_BUILD_UI = r'''
    def _build_ui(self) -> None:
        # 紧凑 LoveLedger 风格 QQ 自动回复控制台。
        for child in self.root_frame.winfo_children():
            child.destroy()

        try:
            _style_text_widget = style_text_widget  # type: ignore[name-defined]
        except Exception:
            _style_text_widget = lambda widget: None

        self.root_frame.configure(style="Paper.TFrame")
        self.root_frame.grid_columnconfigure(0, weight=1)
        self.root_frame.grid_rowconfigure(2, weight=1)
        self.root_frame.grid_rowconfigure(3, weight=0)

        # Header
        header = ttk.Frame(self.root_frame, style="Paper.TFrame")
        header.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 8))
        header.grid_columnconfigure(0, weight=1)

        title_box = ttk.Frame(header, style="Paper.TFrame")
        title_box.grid(row=0, column=0, sticky="w")
        ttk.Label(title_box, text="QQ Bot Overview", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            title_box,
            text="Ledger-style auto reply control panel · grouped settings, live logs, quick actions",
            style="Subtitle.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(2, 0))

        action_bar = ttk.Frame(header, style="Paper.TFrame")
        action_bar.grid(row=0, column=1, sticky="e")
        ttk.Button(action_bar, text="一键启动/填充", command=self.on_qq_bootstrap, style="Primary.TButton").grid(row=0, column=0, padx=(0, 8))
        ttk.Button(action_bar, text="更新配置", command=self.on_qq_configure, style="Success.TButton").grid(row=0, column=1, padx=(0, 8))
        ttk.Button(action_bar, text="查询状态", command=self.on_qq_status, style="Secondary.TButton").grid(row=0, column=2)

        # Metric cards
        cards = ttk.Frame(self.root_frame, style="Paper.TFrame")
        cards.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 10))
        for i in range(4):
            cards.grid_columnconfigure(i, weight=1, uniform="metric")

        def _metric(parent, col, title, value, hint, tag, accent):
            card = tk.Frame(parent, bg="#fff8e8", highlightbackground="#2a2521", highlightthickness=1)
            card.grid(row=0, column=col, sticky="ew", padx=(0 if col == 0 else 10, 0))
            card.grid_columnconfigure(0, weight=1)
            tk.Label(card, text=tag, bg=accent, fg="#fff8e8", font=("Georgia", 6, "bold"), padx=7, pady=2).grid(
                row=0, column=0, sticky="ne", padx=8, pady=(7, 0)
            )
            tk.Label(card, text=title, bg="#fff8e8", fg="#7e5850", font=("Georgia", 9, "bold"), anchor="w").grid(
                row=1, column=0, sticky="ew", padx=12, pady=(0, 0)
            )
            tk.Label(card, text=value, bg="#fff8e8", fg="#26211f", font=("Georgia", 14, "bold"), anchor="w").grid(
                row=2, column=0, sticky="ew", padx=12, pady=(2, 0)
            )
            tk.Label(card, text=hint, bg="#fff8e8", fg="#756c61", font=("Microsoft YaHei UI", 7), anchor="w").grid(
                row=3, column=0, sticky="ew", padx=12, pady=(0, 9)
            )

        _metric(cards, 0, "Auto Reply", "Enabled" if self.qq_enabled_var.get() else "Disabled", "总开关 / 私聊 / 冷却", "AUTO", "#285d52")
        _metric(cards, 1, "Model", self.text_api_model_var.get() or self.text_api_provider_var.get() or "mock", "DeepSeek / Qwen / OpenAI", "AI", "#747a91")
        _metric(cards, 2, "Gateway", self.qq_gateway_var.get() or "managed", "NapCat HTTP / Managed", "NET", "#285d52")
        _metric(cards, 3, "Groups", self.qq_group_var.get() or "demo_chat", "目标群 / 监听范围", "CHAT", "#b85757")

        # Middle: large log + compact actions
        main = ttk.Frame(self.root_frame, style="Paper.TFrame")
        main.grid(row=2, column=0, sticky="nsew", padx=16, pady=(0, 10))
        main.grid_columnconfigure(0, weight=5)
        main.grid_columnconfigure(1, weight=2, minsize=270)
        main.grid_rowconfigure(0, weight=1)

        log_card = ttk.LabelFrame(main, text="Live Ledger · QQ Events", padding=10, style="Card.TLabelframe")
        log_card.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        log_card.grid_columnconfigure(0, weight=1)
        log_card.grid_rowconfigure(0, weight=1)

        self.qq_chat_display = tk.Text(log_card, wrap=tk.WORD, state=tk.DISABLED, font=("Consolas", 10))
        self.qq_chat_display.grid(row=0, column=0, sticky="nsew")
        _style_text_widget(self.qq_chat_display)

        scroll = ttk.Scrollbar(log_card, orient=tk.VERTICAL, command=self.qq_chat_display.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.qq_chat_display.configure(yscrollcommand=scroll.set)

        self.qq_chat_display.tag_configure("msg_in", foreground="#285d52", font=("Microsoft YaHei UI", 10, "bold"))
        self.qq_chat_display.tag_configure("msg_out", foreground="#b85757", font=("Microsoft YaHei UI", 10, "bold"))
        self.qq_chat_display.tag_configure("msg_sys", foreground="#7b7167", font=("Microsoft YaHei UI", 9))

        right = ttk.Frame(main, style="Paper.TFrame")
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_columnconfigure(0, weight=1)

        status_card = tk.Frame(right, bg="#26211f", highlightbackground="#2a2521", highlightthickness=1)
        status_card.grid(row=0, column=0, sticky="ew")
        status_card.grid_columnconfigure(0, weight=1)
        tk.Label(status_card, text="RECENT STATUS", bg="#26211f", fg="#fff8e8", font=("Georgia", 10, "bold"), anchor="w").grid(
            row=0, column=0, sticky="ew", padx=12, pady=(12, 4)
        )
        tk.Label(status_card, textvariable=self.qq_status_text, bg="#26211f", fg="#efe2cb", font=("Microsoft YaHei UI", 8), justify=tk.LEFT, wraplength=250, anchor="w").grid(
            row=1, column=0, sticky="ew", padx=12, pady=(0, 6)
        )
        tk.Label(status_card, textvariable=self.qq_webhook_url_var, bg="#26211f", fg="#c9bda8", font=("Microsoft YaHei UI", 8), justify=tk.LEFT, wraplength=250, anchor="w").grid(
            row=2, column=0, sticky="ew", padx=12, pady=(0, 12)
        )

        action_card = ttk.LabelFrame(right, text="Quick Actions", padding=10, style="Card.TLabelframe")
        action_card.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        for i in range(2):
            action_card.grid_columnconfigure(i, weight=1)
        ttk.Button(action_card, text="下载 NapCat", command=self.on_qq_download_napcat, style="Secondary.TButton").grid(row=0, column=0, sticky="ew", padx=(0, 6), pady=4)
        ttk.Button(action_card, text="绑定客户端", command=self.on_qq_bind_local_client_auto, style="Secondary.TButton").grid(row=0, column=1, sticky="ew", pady=4)
        ttk.Button(action_card, text="轮询待回复", command=self.on_qq_poll_pending, style="Secondary.TButton").grid(row=1, column=0, sticky="ew", padx=(0, 6), pady=4)
        ttk.Button(action_card, text="查询状态", command=self.on_qq_status, style="Secondary.TButton").grid(row=1, column=1, sticky="ew", pady=4)
        ttk.Button(action_card, text="暂停", command=self.on_qq_pause, style="Warning.TButton").grid(row=2, column=0, sticky="ew", padx=(0, 6), pady=4)
        ttk.Button(action_card, text="恢复", command=self.on_qq_resume, style="Success.TButton").grid(row=2, column=1, sticky="ew", pady=4)
        ttk.Button(action_card, text="重启事件服务器", command=self.on_qq_restart_webhook, style="Danger.TButton").grid(row=3, column=0, columnspan=2, sticky="ew", pady=(8, 4))

        # Bottom grouped settings
        settings = ttk.LabelFrame(self.root_frame, text="Ledger Settings · 参数分组", padding=8, style="Card.TLabelframe")
        settings.grid(row=3, column=0, sticky="ew", padx=16, pady=(0, 14))
        settings.grid_columnconfigure(0, weight=1)

        config_tabs = ttk.Notebook(settings, style="Ledger.TNotebook")
        config_tabs.grid(row=0, column=0, sticky="ew")

        # Tab 1
        basic = ttk.Frame(config_tabs, style="Surface.TFrame", padding=10)
        config_tabs.add(basic, text="  Overview 基础  ")
        for i in range(8):
            basic.grid_columnconfigure(i, weight=1)

        ttk.Label(basic, text="目标群号").grid(row=0, column=0, sticky="w")
        ttk.Entry(basic, textvariable=self.qq_group_var).grid(row=0, column=1, columnspan=3, sticky="ew", padx=(8, 14))
        ttk.Label(basic, text="机器人ID").grid(row=0, column=4, sticky="w")
        ttk.Entry(basic, textvariable=self.qq_self_user_var, width=14).grid(row=0, column=5, sticky="ew", padx=(8, 14))
        ttk.Label(basic, text="网关").grid(row=0, column=6, sticky="w")
        ttk.Combobox(basic, textvariable=self.qq_gateway_var, values=["mock", "managed", "windows"], width=10, state="readonly").grid(row=0, column=7, sticky="ew", padx=(8, 0))

        ttk.Label(basic, text="私聊延时").grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(basic, textvariable=self.qq_delay_var, width=8).grid(row=1, column=1, sticky="w", padx=(8, 14), pady=(8, 0))
        ttk.Label(basic, text="冷却秒数").grid(row=1, column=2, sticky="w", pady=(8, 0))
        ttk.Entry(basic, textvariable=self.qq_cooldown_var, width=8).grid(row=1, column=3, sticky="w", padx=(8, 14), pady=(8, 0))
        ttk.Checkbutton(basic, text="启用自动回复", variable=self.qq_enabled_var).grid(row=1, column=4, sticky="w", pady=(8, 0))
        ttk.Checkbutton(basic, text="启用私聊回复", variable=self.qq_private_enabled_var).grid(row=1, column=5, sticky="w", pady=(8, 0))
        ttk.Checkbutton(basic, text="图片识别", variable=self.qq_image_recognition_var).grid(row=1, column=6, sticky="w", pady=(8, 0))
        ttk.Checkbutton(basic, text="连接后立即尝试发送", variable=self.qq_connect_now_var).grid(row=1, column=7, sticky="w", pady=(8, 0))

        ttk.Label(basic, text="猫娘/人格 Prompt").grid(row=2, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(basic, textvariable=self.qq_prompt_var).grid(row=2, column=1, columnspan=7, sticky="ew", padx=(8, 0), pady=(8, 0))

        # Tab 2
        model = ttk.Frame(config_tabs, style="Surface.TFrame", padding=10)
        config_tabs.add(model, text="  Advisor 模型  ")
        for i in range(6):
            model.grid_columnconfigure(i, weight=1)

        ttk.Label(model, text="Provider").grid(row=0, column=0, sticky="w")
        ttk.Combobox(model, textvariable=self.text_api_provider_var, values=["openai", "deepseek", "qwen", "mock"], width=12, state="readonly").grid(row=0, column=1, sticky="ew", padx=(8, 14))
        ttk.Label(model, text="Model").grid(row=0, column=2, sticky="w")
        ttk.Entry(model, textvariable=self.text_api_model_var).grid(row=0, column=3, sticky="ew", padx=(8, 14))
        ttk.Label(model, text="Base URL").grid(row=0, column=4, sticky="w")
        ttk.Entry(model, textvariable=self.text_api_base_url_var).grid(row=0, column=5, sticky="ew", padx=(8, 0))

        ttk.Label(model, text="API Key").grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(model, textvariable=self.text_api_key_var, show="•").grid(row=1, column=1, columnspan=5, sticky="ew", padx=(8, 0), pady=(8, 0))

        # Tab 3
        napcat = ttk.Frame(config_tabs, style="Surface.TFrame", padding=10)
        config_tabs.add(napcat, text="  Vault NapCat  ")
        for i in range(6):
            napcat.grid_columnconfigure(i, weight=1)

        ttk.Label(napcat, text="NapCat API 基址").grid(row=0, column=0, sticky="w")
        ttk.Entry(napcat, textvariable=self.qq_managed_api_base_var).grid(row=0, column=1, columnspan=5, sticky="ew", padx=(8, 0))
        ttk.Label(napcat, text="托管账号").grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(napcat, textvariable=self.qq_managed_account_var).grid(row=1, column=1, sticky="ew", padx=(8, 14), pady=(8, 0))
        ttk.Label(napcat, text="发送 Token").grid(row=1, column=2, sticky="w", pady=(8, 0))
        ttk.Entry(napcat, textvariable=self.qq_managed_token_var, show="•").grid(row=1, column=3, sticky="ew", padx=(8, 14), pady=(8, 0))
        ttk.Label(napcat, text="接收 Token").grid(row=1, column=4, sticky="w", pady=(8, 0))
        ttk.Entry(napcat, textvariable=self.qq_receive_token_var, show="•").grid(row=1, column=5, sticky="ew", padx=(8, 0), pady=(8, 0))
        ttk.Label(
            napcat,
            text="提示：3000 通常是 NapCat HTTP Server；17888/qq/event 是 MiniClaw 接收事件地址。",
            style="Muted.TLabel",
        ).grid(row=2, column=0, columnspan=6, sticky="w", pady=(8, 0))

        # Tab 4
        groups = ttk.Frame(config_tabs, style="Surface.TFrame", padding=10)
        config_tabs.add(groups, text="  Envelopes 群号/模拟  ")
        for i in range(8):
            groups.grid_columnconfigure(i, weight=1)

        ttk.Label(groups, text="群号管理").grid(row=0, column=0, sticky="w")
        ttk.Entry(groups, textvariable=self.qq_group_edit_var, width=14).grid(row=0, column=1, sticky="ew", padx=(8, 8))
        ttk.Button(groups, text="新增", command=self.on_qq_group_add, style="Secondary.TButton").grid(row=0, column=2, sticky="ew", padx=(0, 8))
        ttk.Button(groups, text="删除", command=self.on_qq_group_remove, style="Secondary.TButton").grid(row=0, column=3, sticky="ew", padx=(0, 8))
        ttk.Label(groups, text="改为").grid(row=0, column=4, sticky="w")
        ttk.Entry(groups, textvariable=self.qq_group_new_var, width=14).grid(row=0, column=5, sticky="ew", padx=(8, 8))
        ttk.Button(groups, text="修改", command=self.on_qq_group_update, style="Secondary.TButton").grid(row=0, column=6, sticky="ew")
        ttk.Button(groups, text="更新配置", command=self.on_qq_configure, style="Primary.TButton").grid(row=0, column=7, sticky="ew", padx=(8, 0))

        ttk.Label(groups, text="消息来源").grid(row=1, column=0, sticky="w", pady=(10, 0))
        ttk.Combobox(groups, textvariable=self.qq_source_var, values=["private", "group"], width=10, state="readonly").grid(row=1, column=1, sticky="ew", padx=(8, 8), pady=(10, 0))
        ttk.Label(groups, text="会话ID").grid(row=1, column=2, sticky="w", pady=(10, 0))
        ttk.Entry(groups, textvariable=self.qq_chat_var).grid(row=1, column=3, sticky="ew", padx=(8, 8), pady=(10, 0))
        ttk.Label(groups, text="发送者ID").grid(row=1, column=4, sticky="w", pady=(10, 0))
        ttk.Entry(groups, textvariable=self.qq_sender_var).grid(row=1, column=5, sticky="ew", padx=(8, 8), pady=(10, 0))
        ttk.Label(groups, text="已等待").grid(row=1, column=6, sticky="w", pady=(10, 0))
        ttk.Entry(groups, textvariable=self.qq_waited_sec_var, width=8).grid(row=1, column=7, sticky="ew", padx=(8, 0), pady=(10, 0))

        ttk.Label(groups, text="消息内容").grid(row=2, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(groups, textvariable=self.qq_text_var).grid(row=2, column=1, columnspan=5, sticky="ew", padx=(8, 8), pady=(8, 0))
        ttk.Button(groups, text="模拟收到消息", command=self.on_qq_simulate_message, style="Primary.TButton").grid(row=2, column=6, sticky="ew", padx=(0, 8), pady=(8, 0))
        ttk.Button(groups, text="模拟手动回复", command=self.on_qq_manual_replied, style="Secondary.TButton").grid(row=2, column=7, sticky="ew", pady=(8, 0))
'''


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
    backup = WORKSPACE_APP.with_suffix(".py.bak_compact_loveledger")
    backup.write_text(src, encoding="utf-8")

    if "from clawmini.ui_theme import apply_theme" in src and "style_text_widget" not in src:
        src = src.replace(
            "from clawmini.ui_theme import apply_theme",
            "from clawmini.ui_theme import apply_theme, style_text_widget",
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

    print("✅ 已完成紧凑 LoveLedger QQ 页面改造")
    print(f"备份文件：{backup}")
    print("下一步运行：")
    print("  python -m py_compile .\\src\\clawmini\\workspace_app.py")
    print("  python app.py")


if __name__ == "__main__":
    main()
