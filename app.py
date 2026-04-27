"""Clawmini 可视化调试 APP（根目录入口）。

运行方式：
    python app.py
"""

from __future__ import annotations

import http.server
import json
import queue
import threading
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlparse

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

# 允许在项目根目录直接运行 app.py
import sys

ROOT_DIR = Path(__file__).resolve().parent
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from clawmini.config import AgentConfig
from clawmini.core.agent import ClawminiAgent
from clawmini.adapters.qq_adapter import discover_napcat_http_config
from clawmini.types import ToolCall


class _QQWebhookRequestHandler(http.server.BaseHTTPRequestHandler):
    """接收 NapCat / OneBot 事件的本地 HTTP 入口。"""

    server_version = "ClawminiQQWebhook/1.0"

    def _read_request_body(self) -> bytes:
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length > 0:
            return self.rfile.read(length)

        if str(self.headers.get("Transfer-Encoding", "")).lower() != "chunked":
            return b""

        body = bytearray()
        while True:
            size_line = self.rfile.readline().strip()
            if not size_line:
                break
            try:
                chunk_size = int(size_line.split(b";", 1)[0], 16)
            except ValueError:
                break
            if chunk_size <= 0:
                break
            body.extend(self.rfile.read(chunk_size))
            self.rfile.read(2)
        return bytes(body)

    def do_POST(self) -> None:  # noqa: N802
        if self.path not in {"/qq/event", "/qq/binding"}:
            self.send_error(404, "Not Found")
            return

        raw_body = self._read_request_body()
        try:
            payload = json.loads(raw_body.decode("utf-8")) if raw_body else {}
        except Exception:
            self.send_error(400, "Invalid JSON")
            return
        if not isinstance(payload, dict):
            payload = {"value": payload}

        server = cast(_QQWebhookServer, self.server)
        server.app.response_queue.put(
            (
                "qq_gateway_event",
                {
                    "path": self.path,
                    "payload": payload,
                    "raw_body": raw_body.decode("utf-8", errors="ignore"),
                },
            )
        )
        response = json.dumps({"ok": True, "path": self.path}, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def do_GET(self) -> None:  # noqa: N802
        if self.path not in {"/qq/health", "/qq/event"}:
            self.send_error(404, "Not Found")
            return
        response = json.dumps({"ok": True, "path": self.path}, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        _ = format, args
        return


class _QQWebhookServer(http.server.ThreadingHTTPServer):
    """绑定到 Clawmini app 的本地 webhook 服务器。"""

    app: "ClawminiDebugApp"

    def __init__(self, server_address: tuple[str, int], RequestHandlerClass: type[http.server.BaseHTTPRequestHandler], app: "ClawminiDebugApp") -> None:
        super().__init__(server_address, RequestHandlerClass)
        self.app = app


class ClawminiDebugApp:
    """桌面调试应用。

    功能：
    - 与主 Agent 对话
    - 展示 ReAct 规划轨迹
    - 3.2 开放式请求生成 2-3 个方案
    - 选择方案后一键生成文稿
    """

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Clawmini 可视化调试台")
        self.root.geometry("1200x760")
        self.root.minsize(980, 620)
        self.root.resizable(True, True)
        self.root.grid_rowconfigure(3, weight=0)

        workspace = ROOT_DIR / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)

        self.config = AgentConfig(
            model_provider="mock",
            model_name="clawmini-mock",
            workspace_dir=workspace,
            history_path=workspace / "history.json",
            max_rounds=6,
            show_react_steps=True,
            enable_stream_output=True,
        )
        self.agent = ClawminiAgent(self.config)

        self.stream_output_var = tk.BooleanVar(value=True)
        self.show_trace_var = tk.BooleanVar(value=True)
        self.last_plans: list[dict[str, Any]] = []
        self.selected_plan_index: int | None = None
        self.current_preview_file: Path | None = None
        self.response_queue: queue.Queue[tuple[str, dict[str, Any]]] = queue.Queue()
        self.settings_visible = False
        self.active_feature = "chat"
        self.qq_webhook_server: _QQWebhookServer | None = None
        self.qq_webhook_server_thread: threading.Thread | None = None
        self.qq_webhook_url_var = tk.StringVar(value="NapCat事件接收地址：未启动")
        self.text_api_provider_var = tk.StringVar(value="deepseek")
        self.text_api_model_var = tk.StringVar(value="deepseek-chat")
        self.text_api_key_var = tk.StringVar(value="")
        self.text_api_base_url_var = tk.StringVar(value="https://api.deepseek.com")
        self.draft_followup_mode = False
        self._session_tip = "可在任意页面输入，Ctrl+Enter 发送。"

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        preferred_event_port: int | None = None
        napcat = discover_napcat_http_config([ROOT_DIR])
        event_post_url = str(napcat.get("event_post_url", "")).strip() if isinstance(napcat, dict) else ""
        if event_post_url:
            parsed = urlparse(event_post_url)
            if (parsed.hostname or "").lower() in {"127.0.0.1", "localhost", "::1"} and parsed.port:
                preferred_event_port = parsed.port
        self._start_qq_webhook_server(preferred_port=preferred_event_port)
        self._poll_queue()

    def _build_ui(self) -> None:
        """构建界面。"""
        self.root.grid_rowconfigure(2, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

        top = ttk.Frame(self.root, padding=(10, 10, 10, 6))
        top.grid(row=0, column=0, sticky="ew")
        top.grid_columnconfigure(0, weight=1)
        top.grid_columnconfigure(1, weight=0)

        nav_left = ttk.Frame(top)
        nav_left.grid(row=0, column=0, sticky="w")
        ttk.Label(nav_left, text="Clawmini", font=("Microsoft YaHei UI", 14, "bold")).pack(side=tk.LEFT, padx=(0, 12))

        self.nav_buttons: dict[str, ttk.Button] = {}
        nav_items = [
            ("chat", "① 智能对话/写作"),
            ("qq", "② QQ自动回复"),
            ("image", "③ 图片处理"),
        ]
        for key, label in nav_items:
            btn = ttk.Button(nav_left, text=label, width=18, command=lambda k=key: self._show_feature(k))
            btn.pack(side=tk.LEFT, padx=4)
            self.nav_buttons[key] = btn

        right_tools = ttk.Frame(top)
        right_tools.grid(row=0, column=1, sticky="e")
        ttk.Button(right_tools, text="⚙", width=3, command=self._toggle_settings_panel).pack(side=tk.RIGHT)

        self.settings_panel = ttk.LabelFrame(self.root, text="设置", padding=8)
        ttk.Checkbutton(self.settings_panel, text="流式输出", variable=self.stream_output_var).grid(row=0, column=0, sticky=tk.W)
        ttk.Checkbutton(self.settings_panel, text="显示规划轨迹", variable=self.show_trace_var).grid(row=0, column=1, sticky=tk.W, padx=(10, 0))
        ttk.Label(
            self.settings_panel,
            text=f"工作目录: {self.config.workspace_dir}",
            foreground="#555",
        ).grid(row=1, column=0, columnspan=2, sticky=tk.W, pady=(6, 0))

        ttk.Label(self.settings_panel, text="文本 API", foreground="#333").grid(row=2, column=0, columnspan=2, sticky=tk.W, pady=(6, 0))
        ttk.Label(self.settings_panel, text="Provider:").grid(row=3, column=0, sticky=tk.W, pady=(6, 0))
        ttk.Combobox(
            self.settings_panel,
            textvariable=self.text_api_provider_var,
            values=["openai", "deepseek"],
            width=12,
            state="readonly",
        ).grid(row=3, column=1, sticky=tk.W, pady=(6, 0))

        ttk.Label(self.settings_panel, text="Model:").grid(row=4, column=0, sticky=tk.W, pady=(4, 0))
        ttk.Entry(self.settings_panel, textvariable=self.text_api_model_var, width=24).grid(row=4, column=1, sticky=tk.W, pady=(4, 0))

        ttk.Label(self.settings_panel, text="API Key:").grid(row=5, column=0, sticky=tk.W, pady=(4, 0))
        ttk.Entry(self.settings_panel, textvariable=self.text_api_key_var, width=24, show="*").grid(row=5, column=1, sticky=tk.W, pady=(4, 0))

        ttk.Label(self.settings_panel, text="Base URL:").grid(row=6, column=0, sticky=tk.W, pady=(4, 0))
        ttk.Entry(self.settings_panel, textvariable=self.text_api_base_url_var, width=24).grid(row=6, column=1, sticky=tk.W, pady=(4, 0))

        self.main = ttk.Frame(self.root, padding=(10, 0, 10, 10))
        self.main.grid(row=2, column=0, sticky="nsew")
        self.main.grid_rowconfigure(0, weight=1)
        self.main.grid_columnconfigure(0, weight=1, minsize=320)
        self.main.grid_columnconfigure(1, weight=2)

        self._build_session_panel(self.main)

        self.content = ttk.Frame(self.main, padding=(10, 0, 0, 0))
        self.content.grid(row=0, column=1, sticky="nsew")
        self.content.grid_rowconfigure(0, weight=1)
        self.content.grid_columnconfigure(0, weight=1)

        self.feature_frames: dict[str, ttk.Frame] = {}
        chat_page = ttk.Frame(self.content)
        qq_page = ttk.Frame(self.content)
        image_page = ttk.Frame(self.content)
        self.feature_frames["chat"] = chat_page
        self.feature_frames["qq"] = qq_page
        self.feature_frames["image"] = image_page

        for frame in self.feature_frames.values():
            frame.grid(row=0, column=0, sticky="nsew")

        self._build_chat_page(chat_page)
        self._build_qq_tab(qq_page)
        self._build_image_tab(image_page)

        self._show_feature("chat")

        self._append_chat("系统", "欢迎使用 Clawmini 调试台。\n- 左上选择功能模块\n- 右上齿轮可展开设置")

    def _build_chat_page(self, page: ttk.Frame) -> None:
        """构建智能对话/写作页。"""
        quick = ttk.LabelFrame(page, text="文稿生成（外部API）", padding=8)
        quick.pack(fill=tk.X, pady=(0, 8))

        ttk.Label(
            quick,
            text="输入要求：请填写`主题`（必填）和`具体要求`；可选字数限制。生成并预览后，可在底部全局控制台输入后续补充内容。",
            foreground="#444",
        ).grid(row=0, column=0, columnspan=8, sticky=tk.W, pady=(0, 6))
        ttk.Label(
            quick,
            text="API Key 请点右上角齿轮打开设置，在 API Key 输入框中填写。",
            foreground="#666",
        ).grid(row=0, column=8, columnspan=2, sticky=tk.E, pady=(0, 6))

        ttk.Label(quick, text="主题*: ").grid(row=1, column=0, sticky=tk.W)
        self.draft_topic_var = tk.StringVar(value="")
        ttk.Entry(quick, textvariable=self.draft_topic_var, width=28).grid(row=1, column=1, sticky=tk.W, padx=(0, 8))

        ttk.Label(quick, text="具体要求: ").grid(row=1, column=2, sticky=tk.W)
        self.draft_specific_var = tk.StringVar(value="")
        ttk.Entry(quick, textvariable=self.draft_specific_var, width=36).grid(row=1, column=3, columnspan=3, sticky=tk.W, padx=(0, 8))

        ttk.Label(quick, text="字数(可选):").grid(row=1, column=6, sticky=tk.W)
        self.draft_wordcount_var = tk.StringVar(value="1200")
        ttk.Entry(quick, textvariable=self.draft_wordcount_var, width=8).grid(row=1, column=7, sticky=tk.W, padx=(0, 8))

        ttk.Label(quick, text="文件名:").grid(row=2, column=0, sticky=tk.W, pady=(6, 0))
        self.draft_filename_var = tk.StringVar(value="")
        ttk.Entry(quick, textvariable=self.draft_filename_var, width=24).grid(row=2, column=1, sticky=tk.W, padx=(0, 8), pady=(6, 0))

        ttk.Label(quick, text="输出目录:").grid(row=2, column=2, sticky=tk.W, pady=(6, 0))
        self.draft_output_dir_var = tk.StringVar(value=".")
        ttk.Entry(quick, textvariable=self.draft_output_dir_var, width=22).grid(row=2, column=3, sticky=tk.W, pady=(6, 0))
        ttk.Button(
            quick,
            text="浏览",
            command=lambda: self._browse_workspace_directory(self.draft_output_dir_var, "选择文稿输出目录"),
            width=8,
        ).grid(row=2, column=4, sticky=tk.W, padx=(6, 8), pady=(6, 0))

        ttk.Button(quick, text="生成文稿", command=self.on_create_direct_draft).grid(row=2, column=5, sticky=tk.W, pady=(6, 0))
        ttk.Button(quick, text="生成2-3个方案", command=self.on_brainstorm_from_quick).grid(row=2, column=6, sticky=tk.W, pady=(6, 0), padx=(6, 0))

        notebook = ttk.Notebook(page)
        notebook.pack(fill=tk.BOTH, expand=True)

        trace_tab = ttk.Frame(notebook, padding=8)
        plan_tab = ttk.Frame(notebook, padding=8)
        preview_tab = ttk.Frame(notebook, padding=8)
        notebook.add(trace_tab, text="规划轨迹")
        notebook.add(plan_tab, text="方案选择")
        notebook.add(preview_tab, text="文稿预览")

        self.trace_text = ScrolledText(trace_tab, wrap=tk.WORD, height=16, font=("Consolas", 10))
        self.trace_text.pack(fill=tk.BOTH, expand=True)
        self.trace_text.configure(state=tk.DISABLED)

        ttk.Label(plan_tab, text="候选方案卡片（先生成，再选择其中一个继续生成/修改）", font=("Microsoft YaHei UI", 10, "bold")).pack(anchor=tk.W)

        self.plan_card_vars = [tk.StringVar(value=f"方案{i + 1}：暂无数据") for i in range(3)]
        self.plan_select_buttons = []

        card_container = ttk.Frame(plan_tab)
        card_container.pack(fill=tk.X, pady=(6, 8))

        for idx in range(3):
            frame = ttk.LabelFrame(card_container, text=f"方案{idx + 1}", padding=8)
            frame.pack(fill=tk.X, pady=4)
            ttk.Label(frame, textvariable=self.plan_card_vars[idx], justify=tk.LEFT).pack(anchor=tk.W, fill=tk.X)
            btn = ttk.Button(frame, text=f"选择方案{idx + 1}", command=lambda i=idx: self.on_select_plan(i))
            btn.pack(anchor=tk.E, pady=(6, 0))
            self.plan_select_buttons.append(btn)

        action_row = ttk.Frame(plan_tab)
        action_row.pack(fill=tk.X)

        ttk.Button(action_row, text="按当前选中方案生成文稿", command=self.on_create_from_selected_plan).pack(side=tk.LEFT)
        ttk.Button(action_row, text="显示当前方案详情", command=self.on_show_selected_plan).pack(side=tk.LEFT, padx=8)

        self.plan_detail = ScrolledText(plan_tab, wrap=tk.WORD, height=10, font=("Consolas", 10))
        self.plan_detail.pack(fill=tk.BOTH, expand=True)
        self.plan_detail.configure(state=tk.DISABLED)

        ttk.Label(preview_tab, text="文稿预览（生成后自动加载）", font=("Microsoft YaHei UI", 10, "bold")).pack(anchor=tk.W)
        preview_top = ttk.Frame(preview_tab)
        preview_top.pack(fill=tk.X, pady=(6, 8))
        self.preview_path_var = tk.StringVar(value="当前文件：未加载")
        ttk.Label(preview_top, textvariable=self.preview_path_var, foreground="#444").pack(side=tk.LEFT)
        ttk.Button(preview_top, text="刷新预览", command=self.on_refresh_preview).pack(side=tk.RIGHT)

        self.preview_text = ScrolledText(preview_tab, wrap=tk.WORD, height=24, font=("Consolas", 10))
        self.preview_text.pack(fill=tk.BOTH, expand=True)
        self.preview_text.configure(state=tk.DISABLED)

    def _show_feature(self, feature: str) -> None:
        """切换功能页。"""
        if feature not in self.feature_frames:
            return
        self.active_feature = feature
        self.feature_frames[feature].tkraise()

        active_prefix = "● "
        normal_prefix = "  "
        labels = {
            "chat": "① 智能对话/写作",
            "qq": "② QQ自动回复",
            "image": "③ 图片处理",
        }
        for key, btn in self.nav_buttons.items():
            prefix = active_prefix if key == feature else normal_prefix
            btn.configure(text=prefix + labels[key])

    def _toggle_settings_panel(self) -> None:
        """展开/收起右上设置面板。"""
        self.settings_visible = not self.settings_visible
        if self.settings_visible:
            self.settings_panel.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 6))
        else:
            self.settings_panel.grid_forget()

    def _build_qq_tab(self, tab: ttk.Frame) -> None:
        """构建 3.1 QQ 自动回复调试页。"""
        tab = self._make_scrollable_container(tab)
        ttk.Label(tab, text="QQ自动回复（3.1）", font=("Microsoft YaHei UI", 10, "bold")).pack(anchor=tk.W)

        guide = ttk.LabelFrame(tab, text="操作指引", padding=8)
        guide.pack(fill=tk.X, pady=(8, 6))
        guide_text = (
            "1. 先选网关模式：演示选 mock；无窗口托管选 managed；桌面自动化选 windows。\n"
            "2. 先点“下载NapCat”打开官方发布页，下载 Windows 一键包并完成本地安装。\n"
            "3. 安装后点“一键启动并自动填充”，会自动发现 NapCat、填充账号和 API 基址。\n"
            "4. managed / windows 模式都能通过 NapCat 在线发送。\n"
            "5. 再点“更新QQ配置”保存群号、私聊延时、冷却和账号ID。\n"
            "6. 使用“模拟收到消息”先验证回复逻辑，再切换到真实 QQ。\n"
            "7. 如果提示缺少 pywinauto，请先执行 python -m pip install pywinauto。\n"
            "8. 如果显示失败，先检查 QQ 是否装在默认目录或已经启动。"
        )
        ttk.Label(guide, text=guide_text, justify=tk.LEFT, foreground="#444").pack(anchor=tk.W)

        cfg = ttk.Frame(tab)
        cfg.pack(fill=tk.X, pady=(8, 6))

        ttk.Label(cfg, text="基础配置", font=("Microsoft YaHei UI", 10, "bold")).grid(row=0, column=0, columnspan=6, sticky=tk.W, pady=(0, 6))

        ttk.Label(cfg, text="目标群号(可多个，逗号分隔):").grid(row=1, column=0, sticky=tk.W)
        self.qq_group_var = tk.StringVar(value="demo_chat")
        ttk.Entry(cfg, textvariable=self.qq_group_var, width=24).grid(row=1, column=1, padx=6)

        ttk.Label(cfg, text="私聊延时(秒):").grid(row=1, column=2, sticky=tk.W)
        self.qq_delay_var = tk.IntVar(value=0)
        ttk.Entry(cfg, textvariable=self.qq_delay_var, width=10).grid(row=1, column=3, padx=6)

        ttk.Label(cfg, text="冷却(秒):").grid(row=1, column=4, sticky=tk.W)
        self.qq_cooldown_var = tk.IntVar(value=0)
        ttk.Entry(cfg, textvariable=self.qq_cooldown_var, width=8).grid(row=1, column=5, padx=6)

        ttk.Label(cfg, text="当前账号ID:").grid(row=2, column=0, sticky=tk.W, pady=(8, 0))
        self.qq_self_user_var = tk.StringVar(value="self_user")
        ttk.Entry(cfg, textvariable=self.qq_self_user_var, width=14).grid(row=2, column=1, padx=6, pady=(8, 0))

        ttk.Label(cfg, text="群号管理:").grid(row=3, column=0, sticky=tk.W, pady=(8, 0))
        self.qq_group_edit_var = tk.StringVar(value="")
        ttk.Entry(cfg, textvariable=self.qq_group_edit_var, width=14).grid(row=3, column=1, padx=6, pady=(8, 0), sticky=tk.W)
        ttk.Button(cfg, text="新增", command=self.on_qq_group_add).grid(row=3, column=2, sticky=tk.W, pady=(8, 0))
        ttk.Button(cfg, text="删除", command=self.on_qq_group_remove).grid(row=3, column=3, sticky=tk.W, pady=(8, 0))
        self.qq_group_new_var = tk.StringVar(value="")
        ttk.Entry(cfg, textvariable=self.qq_group_new_var, width=12).grid(row=3, column=4, padx=6, pady=(8, 0), sticky=tk.W)
        ttk.Button(cfg, text="修改", command=self.on_qq_group_update).grid(row=3, column=5, sticky=tk.W, pady=(8, 0))

        self.qq_private_enabled_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(cfg, text="启用私聊回复", variable=self.qq_private_enabled_var).grid(row=2, column=2, sticky=tk.W, pady=(8, 0))
        self.qq_enabled_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(cfg, text="启用自动回复", variable=self.qq_enabled_var).grid(row=2, column=3, sticky=tk.W, pady=(8, 0))

        ttk.Label(cfg, text="网关模式:").grid(row=2, column=4, sticky=tk.W, pady=(8, 0))
        self.qq_gateway_var = tk.StringVar(value="managed")
        ttk.Combobox(cfg, textvariable=self.qq_gateway_var, values=["mock", "managed", "windows"], width=10, state="readonly").grid(row=2, column=5, padx=6, pady=(8, 0))

        self.qq_connect_now_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(cfg, text="连接后立即尝试发送", variable=self.qq_connect_now_var).grid(row=4, column=0, columnspan=2, sticky=tk.W, pady=(8, 0))

        ttk.Label(cfg, text="自定义提示词:").grid(row=5, column=0, sticky=tk.W, pady=(8, 0))
        self.qq_prompt_var = tk.StringVar(value="")
        ttk.Entry(cfg, textvariable=self.qq_prompt_var, width=38).grid(row=5, column=1, columnspan=5, sticky=tk.W, pady=(8, 0))

        managed_row = ttk.LabelFrame(tab, text="managed / NapCat 在线发送", padding=8)
        managed_row.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(managed_row, text="API 基址: ").grid(row=0, column=0, sticky=tk.W)
        self.qq_managed_api_base_var = tk.StringVar(value="http://127.0.0.1:6099/plugin/napcat-plugin-builtin/api")
        ttk.Entry(managed_row, textvariable=self.qq_managed_api_base_var, width=54).grid(row=0, column=1, columnspan=4, sticky=tk.W, padx=6)
        ttk.Label(managed_row, text="Token(可选):").grid(row=1, column=0, sticky=tk.W, pady=(6, 0))
        self.qq_managed_token_var = tk.StringVar(value="")
        ttk.Entry(managed_row, textvariable=self.qq_managed_token_var, width=28, show="*").grid(row=1, column=1, sticky=tk.W, padx=6, pady=(6, 0))
        ttk.Label(managed_row, text="账号ID: ").grid(row=1, column=2, sticky=tk.W, pady=(6, 0))
        self.qq_managed_account_var = tk.StringVar(value="3892874358")
        ttk.Entry(managed_row, textvariable=self.qq_managed_account_var, width=14).grid(row=1, column=3, sticky=tk.W, padx=6, pady=(6, 0))
        ttk.Label(
            managed_row,
            text="说明：先下载并安装 NapCat，再用一键启动自动填充账号与 API 基址；发送时会调用 send_group_msg / send_private_msg。",
            foreground="#666",
        ).grid(row=2, column=0, columnspan=5, sticky=tk.W, pady=(6, 0))

        actions = ttk.Frame(tab)
        actions.pack(fill=tk.X, pady=6)
        ttk.Label(actions, text="快捷操作:", foreground="#444").grid(row=0, column=0, sticky=tk.W, padx=(0, 6), pady=(0, 4))
        ttk.Button(actions, text="下载NapCat", command=self.on_qq_download_napcat).grid(row=0, column=1, sticky=tk.W, padx=(0, 6), pady=(0, 4))
        ttk.Button(actions, text="一键启动/填充", command=self.on_qq_bootstrap).grid(row=0, column=2, sticky=tk.W, padx=(0, 6), pady=(0, 4))
        ttk.Button(actions, text="更新配置", command=self.on_qq_configure).grid(row=0, column=3, sticky=tk.W, padx=(0, 6), pady=(0, 4))
        ttk.Button(actions, text="一键绑定客户端", command=self.on_qq_bind_local_client_auto).grid(row=1, column=1, sticky=tk.W, padx=(0, 6))
        ttk.Button(actions, text="查询状态", command=self.on_qq_status).grid(row=1, column=2, sticky=tk.W, padx=(0, 6))
        ttk.Button(actions, text="轮询待回复", command=self.on_qq_poll_pending).grid(row=1, column=3, sticky=tk.W, padx=(0, 6))
        ttk.Button(actions, text="暂停", command=self.on_qq_pause).grid(row=2, column=1, sticky=tk.W, padx=(0, 6), pady=(4, 0))
        ttk.Button(actions, text="恢复", command=self.on_qq_resume).grid(row=2, column=2, sticky=tk.W, padx=(0, 6), pady=(4, 0))

        simulate = ttk.LabelFrame(tab, text="消息模拟", padding=8)
        simulate.pack(fill=tk.X, pady=8)
        ttk.Label(simulate, text="先用这里测试回复规则，确认没问题后再接真实 QQ。", foreground="#666").grid(row=0, column=0, columnspan=4, sticky=tk.W, pady=(0, 6))
        ttk.Label(simulate, text="QQ 回复会复用右上角设置里的 API 配置；未填 API Key 时会回退为默认回复。", foreground="#666").grid(row=0, column=4, columnspan=2, sticky=tk.W, pady=(0, 6), padx=(8, 0))
        self.qq_source_var = tk.StringVar(value="private")
        ttk.Label(simulate, text="消息来源:").grid(row=1, column=0, sticky=tk.W)
        ttk.Combobox(simulate, textvariable=self.qq_source_var, values=["private", "group"], width=10, state="readonly").grid(row=1, column=1, sticky=tk.W)
        self.qq_chat_var = tk.StringVar(value="demo_chat")
        ttk.Label(simulate, text="会话ID（私聊=对方账号/群聊=群号）:").grid(row=1, column=2, sticky=tk.W, padx=(12, 0))
        ttk.Entry(simulate, textvariable=self.qq_chat_var, width=14).grid(row=1, column=3, padx=6)
        self.qq_sender_var = tk.StringVar(value="user_001")
        ttk.Label(simulate, text="发送者ID:").grid(row=2, column=0, sticky=tk.W, pady=(8, 0))
        ttk.Entry(simulate, textvariable=self.qq_sender_var, width=14).grid(row=2, column=1, padx=6, pady=(8, 0))
        ttk.Label(simulate, text="私聊已等待(秒):").grid(row=2, column=2, sticky=tk.W, pady=(8, 0), padx=(12, 0))
        self.qq_waited_sec_var = tk.IntVar(value=0)
        ttk.Entry(simulate, textvariable=self.qq_waited_sec_var, width=8).grid(row=2, column=3, padx=6, pady=(8, 0), sticky=tk.W)
        self.qq_text_var = tk.StringVar(value="你好，请帮我回复")
        ttk.Label(simulate, text="消息内容:").grid(row=3, column=0, sticky=tk.W, pady=(8, 0))
        ttk.Entry(simulate, textvariable=self.qq_text_var, width=32).grid(row=3, column=1, columnspan=3, pady=(8, 0), sticky=tk.W)
        ttk.Button(simulate, text="模拟收到消息", command=self.on_qq_simulate_message).grid(row=1, column=4, rowspan=3, padx=8, sticky=tk.NS)
        ttk.Button(simulate, text="模拟用户手动回复(取消)", command=self.on_qq_manual_replied).grid(row=1, column=5, rowspan=3, padx=6, sticky=tk.NS)

        info = ttk.LabelFrame(tab, text="运行信息", padding=8)
        info.pack(fill=tk.X, pady=(0, 6))
        self.qq_status_text = tk.StringVar(value="状态：未查询。建议先看上方操作指引，再点“一键启动/填充”。")
        ttk.Label(info, textvariable=self.qq_status_text, foreground="#444").pack(anchor=tk.W)
        ttk.Label(info, textvariable=self.qq_webhook_url_var, foreground="#666").pack(anchor=tk.W, pady=(4, 0))

    def _build_image_tab(self, tab: ttk.Frame) -> None:
        """构建 3.3 图片处理调试页。"""
        ttk.Label(tab, text="批量图片处理（3.3）", font=("Microsoft YaHei UI", 10, "bold")).pack(anchor=tk.W)

        path_row = ttk.Frame(tab)
        path_row.pack(fill=tk.X, pady=(8, 6))
        ttk.Label(path_row, text="输入目录(相对workspace):").pack(side=tk.LEFT)
        self.img_input_var = tk.StringVar(value="images")
        ttk.Entry(path_row, textvariable=self.img_input_var, width=20).pack(side=tk.LEFT, padx=6)
        ttk.Button(
            path_row,
            text="浏览",
            width=8,
            command=lambda: self._browse_workspace_directory(self.img_input_var, "选择图片输入目录"),
        ).pack(side=tk.LEFT)
        ttk.Label(path_row, text="输出目录:").pack(side=tk.LEFT)
        self.img_output_var = tk.StringVar(value="output")
        ttk.Entry(path_row, textvariable=self.img_output_var, width=20).pack(side=tk.LEFT, padx=6)
        ttk.Button(
            path_row,
            text="浏览",
            width=8,
            command=lambda: self._browse_workspace_directory(self.img_output_var, "选择图片输出目录"),
        ).pack(side=tk.LEFT)

        ttk.Label(tab, text="说明：目录选择仅允许工作目录内路径，确保本地文件安全。", foreground="#666").pack(anchor=tk.W)

        opt_row = ttk.Frame(tab)
        opt_row.pack(fill=tk.X, pady=6)
        ttk.Label(opt_row, text="格式:").pack(side=tk.LEFT)
        self.img_fmt_var = tk.StringVar(value="png")
        ttk.Combobox(opt_row, textvariable=self.img_fmt_var, values=["png", "jpg", "webp"], width=8, state="readonly").pack(side=tk.LEFT, padx=6)
        ttk.Label(opt_row, text="宽:").pack(side=tk.LEFT)
        self.img_w_var = tk.IntVar(value=1024)
        ttk.Entry(opt_row, textvariable=self.img_w_var, width=8).pack(side=tk.LEFT, padx=4)
        ttk.Label(opt_row, text="高:").pack(side=tk.LEFT)
        self.img_h_var = tk.IntVar(value=768)
        ttk.Entry(opt_row, textvariable=self.img_h_var, width=8).pack(side=tk.LEFT, padx=4)
        self.img_keep_ratio_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(opt_row, text="保持比例", variable=self.img_keep_ratio_var).pack(side=tk.LEFT, padx=8)


        opt_row2 = ttk.Frame(tab)
        opt_row2.pack(fill=tk.X, pady=6)
        self.img_overwrite_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(opt_row2, text="覆盖同名文件", variable=self.img_overwrite_var).pack(side=tk.LEFT)
        self.img_confirm_lossy_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(opt_row2, text="允许 GIF 转 PNG 有损", variable=self.img_confirm_lossy_var).pack(side=tk.LEFT, padx=8)
        ttk.Label(opt_row2, text="起始序号:").pack(side=tk.LEFT, padx=(12, 2))
        self.img_start_index_var = tk.IntVar(value=1)
        ttk.Entry(opt_row2, textvariable=self.img_start_index_var, width=6).pack(side=tk.LEFT)
        ttk.Label(opt_row2, text="补零宽度:").pack(side=tk.LEFT, padx=(12, 2))
        self.img_pad_width_var = tk.IntVar(value=3)
        ttk.Entry(opt_row2, textvariable=self.img_pad_width_var, width=6).pack(side=tk.LEFT)

        opt_row3 = ttk.Frame(tab)
        opt_row3.pack(fill=tk.X, pady=6)
        ttk.Label(opt_row3, text="命名模式:").pack(side=tk.LEFT)
        self.img_pattern_var = tk.StringVar(value="img_{index}")
        ttk.Entry(opt_row3, textvariable=self.img_pattern_var, width=22).pack(side=tk.LEFT, padx=6)
        ttk.Label(opt_row3, text="单图超时(秒):").pack(side=tk.LEFT)
        self.img_timeout_var = tk.DoubleVar(value=30.0)
        ttk.Entry(opt_row3, textvariable=self.img_timeout_var, width=8).pack(side=tk.LEFT, padx=6)

        request_box = ttk.LabelFrame(tab, text="自然语言需求", padding=8)
        request_box.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(request_box, text="可以直接输入中文描述，例如：把所有 JPEG 调整为 1024x768，转成 PNG，重命名为 img_001.png，保存到 output/。", foreground="#666").pack(anchor=tk.W)
        self.img_request_text = tk.Text(request_box, height=3, wrap=tk.WORD, font=("Microsoft YaHei UI", 10))
        self.img_request_text.pack(fill=tk.X, expand=True, pady=(6, 0))
        task_row = ttk.Frame(tab)
        task_row.pack(fill=tk.X, pady=6)
        ttk.Button(task_row, text="执行图片任务", command=self.on_image_process).pack(side=tk.LEFT)
        ttk.Button(task_row, text="查询任务状态", command=self.on_image_task_status).pack(side=tk.LEFT, padx=6)
        ttk.Button(task_row, text="取消任务", command=self.on_image_cancel).pack(side=tk.LEFT, padx=6)
        self.img_task_var = tk.StringVar(value="")
        ttk.Entry(task_row, textvariable=self.img_task_var, width=16).pack(side=tk.LEFT, padx=4)
        ttk.Label(task_row, text="(task_id)", foreground="#666").pack(side=tk.LEFT)

    def _sync_qq_ui_from_status(self, status: dict[str, Any]) -> None:
        """把 QQ 工具状态回填到界面控件。"""
        if not isinstance(status, dict):
            return
        if status.get("target_group_id") is not None:
            self.qq_group_var.set(str(status.get("target_group_id", self.qq_group_var.get())))
        if status.get("self_user_id") is not None:
            self.qq_self_user_var.set(str(status.get("self_user_id", self.qq_self_user_var.get())))
        if status.get("gateway_mode") is not None:
            self.qq_gateway_var.set(str(status.get("gateway_mode", self.qq_gateway_var.get())))
        if status.get("private_delay_sec") is not None:
            self.qq_delay_var.set(int(status.get("private_delay_sec", self.qq_delay_var.get())))
        if status.get("cooldown_sec") is not None:
            self.qq_cooldown_var.set(int(status.get("cooldown_sec", self.qq_cooldown_var.get())))
        if status.get("enabled") is not None:
            self.qq_enabled_var.set(bool(status.get("enabled")))
        if status.get("private_enabled") is not None:
            self.qq_private_enabled_var.set(bool(status.get("private_enabled")))
        if status.get("managed_account") is not None:
            self.qq_managed_account_var.set(str(status.get("managed_account", self.qq_managed_account_var.get())))
        if status.get("managed_api_base_url") is not None:
            self.qq_managed_api_base_var.set(str(status.get("managed_api_base_url", self.qq_managed_api_base_var.get())))
        if status.get("managed_access_token") is not None:
            self.qq_managed_token_var.set(str(status.get("managed_access_token", self.qq_managed_token_var.get())))

        binding = status.get("binding") if isinstance(status.get("binding"), dict) else None
        if isinstance(binding, dict) and binding.get("notes"):
            self.session_tip_var.set(f"{self._session_tip} | 绑定反馈：{binding.get('notes')}")
        elif status.get("gateway_mode") == "managed" and status.get("managed_api_base_url"):
            self.session_tip_var.set(f"{self._session_tip} | NapCat：{status.get('managed_api_base_url')}")
        else:
            self.session_tip_var.set(self._session_tip)

    def _set_qq_status_message(self, message: str, *, speaker: str = "NapCat") -> None:
        """同时更新运行信息与会话区。"""
        self.qq_status_text.set(message)
        self._append_chat(speaker, message, stream=False)

    def _qq_status_number(self, status: dict[str, Any], key: str, fallback_var: tk.IntVar) -> int:
        """优先使用状态值，缺失时回退到当前输入框数值。"""
        value = status.get(key) if isinstance(status, dict) else None
        if value is None:
            return int(fallback_var.get())
        try:
            return int(value)
        except (TypeError, ValueError):
            return int(fallback_var.get())

    def _qq_status_text_from_status(self, status: dict[str, Any]) -> str:
        """生成 QQ 状态摘要，避免数值字段显示为 None。"""
        group_id = str(status.get("target_group_id") or self.qq_group_var.get().strip())
        delay_sec = self._qq_status_number(status, "private_delay_sec", self.qq_delay_var)
        cooldown_sec = self._qq_status_number(status, "cooldown_sec", self.qq_cooldown_var)
        enabled = bool(status.get("enabled") if status.get("enabled") is not None else self.qq_enabled_var.get())
        private_enabled = bool(status.get("private_enabled") if status.get("private_enabled") is not None else self.qq_private_enabled_var.get())
        self_user = str(status.get("self_user_id") or self.qq_self_user_var.get().strip())
        gateway_mode = str(status.get("gateway_mode") or self.qq_gateway_var.get().strip())
        token_value = str(status.get("managed_access_token") or self.qq_managed_token_var.get().strip())
        token_state = token_value if token_value else "未配置"
        return (
            f"配置已更新：enabled={enabled} private={private_enabled} group={group_id} "
            f"delay={delay_sec}s cooldown={cooldown_sec}s self={self_user} gateway={gateway_mode} token={token_state}"
        )

    def _start_qq_webhook_server(self, preferred_port: int | None = None) -> None:
        """启动本地 NapCat 事件接收服务。"""
        if self.qq_webhook_server is not None:
            return

        ports: list[int] = []
        if isinstance(preferred_port, int) and preferred_port > 0:
            ports.append(preferred_port)
        for port in range(17888, 17920):
            if port not in ports:
                ports.append(port)

        for port in ports:
            try:
                server = _QQWebhookServer(("127.0.0.1", port), _QQWebhookRequestHandler, self)
            except OSError:
                continue
            self.qq_webhook_server = server
            self.qq_webhook_server_thread = threading.Thread(target=server.serve_forever, daemon=True)
            self.qq_webhook_server_thread.start()
            webhook_url = f"NapCat事件接收地址：http://127.0.0.1:{port}/qq/event"
            self.qq_webhook_url_var.set(webhook_url)
            self._session_tip = f"{self._session_tip} | {webhook_url}"
            if hasattr(self, "session_tip_var"):
                self.session_tip_var.set(self._session_tip)
            self._append_chat("NapCat", f"事件接收服务已启动：{webhook_url}", stream=False)
            if isinstance(preferred_port, int) and preferred_port > 0 and preferred_port != port:
                self._append_chat(
                    "NapCat",
                    f"注意：NapCat 事件上报端口偏好为 {preferred_port}，当前监听端口为 {port}。请统一 onebot11 的 httpClients.url 与本地监听端口。",
                    stream=False,
                )
            return

        self.qq_webhook_url_var.set("NapCat事件接收地址：启动失败，端口被占用。")
        self._append_chat("NapCat", "事件接收服务启动失败：端口被占用。", stream=False)

    def _ensure_webhook_matches_event_url(self, event_post_url: str) -> None:
        parsed = urlparse(event_post_url.strip())
        host = (parsed.hostname or "").lower()
        if host not in {"127.0.0.1", "localhost", "::1"}:
            return
        if not parsed.port:
            return
        current_port = self.qq_webhook_server.server_address[1] if self.qq_webhook_server is not None else None
        if current_port == parsed.port:
            return
        self._stop_qq_webhook_server()
        self._start_qq_webhook_server(preferred_port=parsed.port)

    def _stop_qq_webhook_server(self) -> None:
        """停止本地 NapCat 事件接收服务。"""
        server = self.qq_webhook_server
        self.qq_webhook_server = None
        if server is not None:
            try:
                server.shutdown()
            finally:
                server.server_close()

    def _on_close(self) -> None:
        """关闭窗口前清理后台服务。"""
        self._stop_qq_webhook_server()
        self.root.destroy()

    def _build_session_panel(self, parent: ttk.Frame) -> None:
        """构建所有页面共用的左侧会话区。"""
        panel = ttk.LabelFrame(parent, text="会话区", padding=8)
        panel.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        panel.grid_rowconfigure(1, weight=1)
        panel.grid_columnconfigure(0, weight=1)

        self.session_tip_var = tk.StringVar(value=self._session_tip)
        ttk.Label(panel, textvariable=self.session_tip_var, foreground="#666", wraplength=250, justify=tk.LEFT).grid(row=0, column=0, sticky=tk.W, pady=(0, 6))

        self.chat_text = ScrolledText(panel, wrap=tk.WORD, height=28, font=("Consolas", 10))
        self.chat_text.grid(row=1, column=0, sticky="nsew")
        self.chat_text.configure(state=tk.DISABLED)

        input_row = ttk.Frame(panel)
        input_row.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        input_row.grid_columnconfigure(0, weight=1)

        self.user_input = tk.Text(input_row, height=4, wrap=tk.WORD, font=("Microsoft YaHei UI", 10))
        self.user_input.grid(row=0, column=0, sticky="ew")
        self.user_input.bind("<Control-Return>", lambda _e: self.on_send())

        btn_col = ttk.Frame(input_row)
        btn_col.grid(row=0, column=1, sticky="ns", padx=(8, 0))
        ttk.Button(btn_col, text="发送消息", command=self.on_send).pack(fill=tk.X, pady=2)
        ttk.Button(btn_col, text="清空聊天", command=self.clear_chat).pack(fill=tk.X, pady=2)

    def _make_scrollable_container(self, parent: ttk.Frame) -> ttk.Frame:
        """为内容较多的页面生成滚动容器。"""
        parent.grid_rowconfigure(0, weight=1)
        parent.grid_columnconfigure(0, weight=1)
        canvas = tk.Canvas(parent, highlightthickness=0)
        scrollbar = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=canvas.yview)
        body = ttk.Frame(canvas)

        body_window = canvas.create_window((0, 0), window=body, anchor="nw")

        def _sync_scrollregion(_event: tk.Event[Any]) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _sync_body_width(event: tk.Event[Any]) -> None:
            canvas.itemconfigure(body_window, width=event.width)

        body.bind("<Configure>", _sync_scrollregion)
        canvas.bind("<Configure>", _sync_body_width)
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        return body

    def on_send(self) -> str | None:
        """发送普通请求到 Agent。"""
        text = self.user_input.get("1.0", tk.END).strip()
        if not text:
            return None
        self.user_input.delete("1.0", tk.END)
        if self.draft_followup_mode and self.current_preview_file is not None:
            self._append_chat("你", f"[后续补充] {text}")
            self._append_chat("系统", "已接收后续补充，正在预览并提交修改...")
            self._run_async(
                "draft_followup",
                {
                    "file_path": str(self.current_preview_file),
                    "instruction": text,
                },
            )
            return "break"

        self._append_chat("你", text)
        self._run_async("agent_message", {"text": text})
        return "break"

    def on_brainstorm(self) -> None:
        """生成 2-3 个候选写作方案。"""
        request = self.user_input.get("1.0", tk.END).strip()
        if not request:
            messagebox.showwarning("提示", "请先在输入框填写写作请求。")
            return
        self.user_input.delete("1.0", tk.END)
        self._append_chat("你", f"[生成方案] {request}")
        self._append_chat("系统", "正在生成 2-3 个候选方案，请稍候。")
        self._run_async("brainstorm", {"request": request})

    def on_brainstorm_from_quick(self) -> None:
        """使用快捷区提示词生成 2-3 个候选方案。"""
        topic = self.draft_topic_var.get().strip()
        specific = self.draft_specific_var.get().strip()
        prompt = "；".join([item for item in [f"主题：{topic}" if topic else "", f"具体要求：{specific}" if specific else ""] if item]).strip()
        if not prompt:
            messagebox.showwarning("提示", "请先填写“主题*”或“具体要求”。")
            return
        self._append_chat("你", f"[生成方案] {prompt}")
        self._append_chat("系统", "正在生成 2-3 个候选方案，请稍候。")
        self._run_async("brainstorm", {"request": prompt})

    def on_create_direct_draft(self) -> None:
        """使用快捷输入直接生成文稿。"""
        topic = self.draft_topic_var.get().strip()
        if not topic:
            messagebox.showwarning("提示", "请先填写“主题*”。")
            return
        api_options = self._collect_text_api_options()
        if api_options is None:
            return
        self.draft_followup_mode = False
        self._append_chat("系统", "已开始调用通用文本 API 生成文稿，请稍候。")
        self._run_async(
            "create_direct",
            {
                "topic": topic,
                "filename": self.draft_filename_var.get().strip(),
                "output_dir": self.draft_output_dir_var.get().strip() or ".",
                "custom_prompt": self.draft_specific_var.get().strip(),
                "word_count": int(self.draft_wordcount_var.get() or 0) if (self.draft_wordcount_var.get().strip()) else None,
                **api_options,
            },
        )

    def on_create_from_selected_plan(self) -> None:
        """根据当前选中的方案生成文稿。"""
        if self.selected_plan_index is None:
            messagebox.showinfo("提示", "请先生成并选择一个方案。")
            return
        idx = self.selected_plan_index
        if idx >= len(self.last_plans):
            messagebox.showerror("错误", "方案索引无效。")
            return
        plan = self.last_plans[idx]
        api_options = self._collect_text_api_options()
        if api_options is None:
            return
        self._append_chat("系统", f"已选择方案{idx + 1}，开始生成文稿。")
        self._run_async(
            "create_from_plan",
            {
                "plan": plan,
                "filename": self.draft_filename_var.get().strip(),
                "output_dir": self.draft_output_dir_var.get().strip() or ".",
                "custom_prompt": self.draft_specific_var.get().strip(),
                **api_options,
            },
        )

    def _collect_text_api_options(self) -> dict[str, Any] | None:
        """收集文本 API 配置。"""
        provider = self.text_api_provider_var.get().strip().lower() or "deepseek"
        model = self.text_api_model_var.get().strip()
        api_key = self.text_api_key_var.get().strip()
        api_base_url = self.text_api_base_url_var.get().strip()
        if not api_key:
            messagebox.showwarning("外部API未配置", "请先在设置中填写 API Key。")
            return None
        return {
            "api_provider": provider,
            "api_model": model,
            "api_key": api_key,
            "api_base_url": api_base_url,
        }

    def _browse_workspace_directory(self, target_var: tk.StringVar, title: str) -> None:
        """浏览并选择工作目录内文件夹。"""
        selected = filedialog.askdirectory(
            title=title,
            initialdir=str(self.config.workspace_dir),
            mustexist=False,
        )
        if not selected:
            return

        selected_path = Path(selected).resolve()
        workspace = self.config.workspace_dir.resolve()
        try:
            rel = selected_path.relative_to(workspace)
            target_var.set("." if str(rel) == "." else rel.as_posix())
        except ValueError:
            messagebox.showwarning("路径限制", f"请在工作目录内选择文件夹：\n{workspace}")

    def _browse_workspace_file(self, target_var: tk.StringVar, title: str) -> None:
        """浏览并选择文件路径。"""
        selected = filedialog.askopenfilename(
            title=title,
            initialdir=str(self.config.workspace_dir),
            filetypes=[("可执行文件", "*.exe"), ("所有文件", "*.*")],
        )
        if not selected:
            return

        target_var.set(str(Path(selected).resolve()))

    def on_show_selected_plan(self) -> None:
        """显示当前选中方案详情。"""
        if self.selected_plan_index is None:
            self._set_text(self.plan_detail, "尚未选择方案。")
            return
        idx = self.selected_plan_index
        if idx >= len(self.last_plans):
            self._set_text(self.plan_detail, "方案索引无效。")
            return
        plan = self.last_plans[idx]
        lines = [
            f"方案{idx + 1}",
            f"- topic: {plan.get('topic')}",
            f"- style: {plan.get('style')}",
            f"- word_count: {plan.get('word_count')}",
            f"- filename: {plan.get('filename')}",
            f"- rationale: {plan.get('rationale')}",
        ]
        preview = str(plan.get("preview_content", "")).strip()
        if preview:
            lines.extend(["", "--- 正文预览 ---", preview])
        else:
            lines.extend(["", "正文预览生成中..."])
            api_options = self._collect_text_api_options()
            if api_options is None:
                self._set_text(self.plan_detail, "\n".join(lines + ["", "请先在右上角设置 API Key。"]))
                return
            self._run_async(
                "preview_plan",
                {
                    "index": idx,
                    "plan": plan,
                        "custom_prompt": self.draft_specific_var.get().strip(),
                    **api_options,
                },
            )
        self._set_text(self.plan_detail, "\n".join(lines))

    def on_select_plan(self, idx: int) -> None:
        """选择指定方案卡片。"""
        if idx >= len(self.last_plans):
            messagebox.showinfo("提示", "该方案暂无数据，请先生成方案。")
            return
        self.selected_plan_index = idx
        self._append_chat("系统", f"已选择方案{idx + 1}。")
        self.on_show_selected_plan()

    def on_refresh_preview(self) -> None:
        """手动刷新当前文稿预览。"""
        if self.current_preview_file is None:
            messagebox.showinfo("提示", "当前没有可预览文稿。")
            return
        self._load_preview_file(self.current_preview_file)

    def on_qq_configure(self) -> None:
        group_ids = [item.strip() for item in self.qq_group_var.get().replace("，", ",").split(",") if item.strip()]
        reply_api = {
            "api_provider": self.text_api_provider_var.get().strip().lower() or "deepseek",
            "api_model": self.text_api_model_var.get().strip(),
            "api_key": self.text_api_key_var.get().strip(),
            "api_base_url": self.text_api_base_url_var.get().strip(),
        }
        self._run_async(
            "qq_configure",
            {
                "enabled": bool(self.qq_enabled_var.get()),
                "private_enabled": bool(self.qq_private_enabled_var.get()),
                "target_group_id": self.qq_group_var.get().strip(),
                "target_group_ids": group_ids,
                "private_delay_sec": int(self.qq_delay_var.get()),
                "custom_prompt": self.qq_prompt_var.get().strip(),
                "cooldown_sec": int(self.qq_cooldown_var.get()),
                "self_user_id": self.qq_self_user_var.get().strip(),
                "gateway_mode": self.qq_gateway_var.get().strip(),
                "managed_account": self.qq_managed_account_var.get().strip(),
                "managed_api_base_url": self.qq_managed_api_base_var.get().strip(),
                "managed_access_token": self.qq_managed_token_var.get().strip(),
                **reply_api,
            },
        )
        if self.qq_managed_token_var.get().strip():
            self._set_qq_status_message("Token已更新成功，等待配置同步。")
        if reply_api.get("api_key"):
            self._append_chat("系统", "已使用文本 API 配置，QQ 回复与文稿生成共用同一组 Provider/Model/Key/Base URL。")

    def on_qq_bootstrap(self) -> None:
        napcat = discover_napcat_http_config([ROOT_DIR])
        if napcat:
            if napcat.get("account_id"):
                self.qq_managed_account_var.set(napcat["account_id"])
                if self.qq_self_user_var.get().strip() in {"", "self_user"}:
                    self.qq_self_user_var.set(napcat["account_id"])
            if napcat.get("api_base_url"):
                self.qq_managed_api_base_var.set(napcat["api_base_url"])
            event_post_url = str(napcat.get("event_post_url", "")).strip()
            if event_post_url:
                self._ensure_webhook_matches_event_url(event_post_url)
        self._run_async(
            "qq_bootstrap",
            {
                "gateway_mode": self.qq_gateway_var.get().strip(),
                "connect_now": bool(self.qq_connect_now_var.get()),
                "managed_account": self.qq_managed_account_var.get().strip(),
                "managed_api_base_url": self.qq_managed_api_base_var.get().strip(),
                "managed_access_token": self.qq_managed_token_var.get().strip(),
                "search_roots": [str(ROOT_DIR)],
            },
        )
        if self.qq_managed_token_var.get().strip():
            self._set_qq_status_message("Token已更新成功，已尝试同步到 NapCat 配置。")

    def on_qq_download_napcat(self) -> None:
        self._run_async("qq_download_napcat", {})

    def on_qq_group_add(self) -> None:
        group_id = self.qq_group_edit_var.get().strip()
        if not group_id:
            messagebox.showwarning("提示", "请输入要新增的群号。")
            return
        self._run_async("qq_group_add", {"group_id": group_id})

    def on_qq_group_remove(self) -> None:
        group_id = self.qq_group_edit_var.get().strip()
        if not group_id:
            messagebox.showwarning("提示", "请输入要删除的群号。")
            return
        self._run_async("qq_group_remove", {"group_id": group_id})

    def on_qq_group_update(self) -> None:
        old_group_id = self.qq_group_edit_var.get().strip()
        new_group_id = self.qq_group_new_var.get().strip()
        if not old_group_id or not new_group_id:
            messagebox.showwarning("提示", "请输入旧群号和新群号。")
            return
        self._run_async("qq_group_update", {"old_group_id": old_group_id, "new_group_id": new_group_id})

    def on_qq_bind_local_client_auto(self) -> None:
        self._run_async(
            "qq_bind_local_client_auto",
            {
                "gateway_mode": self.qq_gateway_var.get().strip(),
                "connect_now": bool(self.qq_connect_now_var.get()),
                "managed_account": self.qq_managed_account_var.get().strip(),
                "managed_api_base_url": self.qq_managed_api_base_var.get().strip(),
                "managed_access_token": self.qq_managed_token_var.get().strip(),
            },
        )

    def on_qq_status(self) -> None:
        self._run_async("qq_status", {})

    def on_qq_pause(self) -> None:
        self._run_async("qq_pause", {})

    def on_qq_resume(self) -> None:
        self._run_async("qq_resume", {})

    def on_qq_poll_pending(self) -> None:
        self._run_async("qq_poll_pending", {})

    def on_qq_simulate_message(self) -> None:
        source = self.qq_source_var.get()
        reply_api = {
            "api_provider": self.text_api_provider_var.get().strip().lower() or "deepseek",
            "api_model": self.text_api_model_var.get().strip(),
            "api_key": self.text_api_key_var.get().strip(),
            "api_base_url": self.text_api_base_url_var.get().strip(),
        }
        self._run_async(
            "qq_simulate",
            {
                "source": source,
                "chat_id": self.qq_chat_var.get().strip(),
                "sender_id": self.qq_sender_var.get().strip(),
                "text": self.qq_text_var.get().strip(),
                "waited_sec": int(self.qq_waited_sec_var.get()) if source == "private" else None,
                **reply_api,
            },
        )

    def on_qq_manual_replied(self) -> None:
        self._run_async("qq_user_replied", {"chat_id": self.qq_chat_var.get().strip()})

    def on_image_process(self) -> None:
        self._run_async(
            "image_process",
            {
                "input_dir": self.img_input_var.get().strip(),
                "output_dir": self.img_output_var.get().strip(),
                "target_format": self.img_fmt_var.get().strip(),
                "width": int(self.img_w_var.get()),
                "height": int(self.img_h_var.get()),
                "keep_ratio": bool(self.img_keep_ratio_var.get()),
                "overwrite": bool(self.img_overwrite_var.get()),
                "confirm_lossy": bool(self.img_confirm_lossy_var.get()),
                "start_index": int(self.img_start_index_var.get()),
                "pad_width": int(self.img_pad_width_var.get()),
                "pattern": self.img_pattern_var.get().strip() or "img_{index}",
                "per_image_timeout_sec": float(self.img_timeout_var.get()),
                "request": self.img_request_text.get("1.0", tk.END).strip(),
            },
        )

    def on_image_task_status(self) -> None:
        self._run_async("image_status", {"task_id": self.img_task_var.get().strip()})

    def on_image_cancel(self) -> None:
        self._run_async("image_cancel", {"task_id": self.img_task_var.get().strip()})

    def clear_chat(self) -> None:
        """清空聊天与轨迹显示区。"""
        self._set_text(self.chat_text, "")
        self._set_text(self.trace_text, "")

    def _run_async(self, action: str, payload: dict[str, Any]) -> None:
        """后台线程执行，避免 UI 卡顿。"""
        thread = threading.Thread(target=self._worker, args=(action, payload), daemon=True)
        thread.start()

    def _worker(self, action: str, payload: dict[str, Any]) -> None:
        """后台任务执行函数。"""
        try:
            if action == "agent_message":
                text = str(payload["text"])
                result = self.agent.handle_user_input_verbose(text)
                self.response_queue.put(
                    (
                        "agent_message",
                        {
                            "answer": result.final_answer,
                            "traces": result.traces,
                        },
                    )
                )
                return

            if action == "brainstorm":
                request = str(payload["request"])
                tool_result = self.agent.registry.execute(
                    ToolCall(
                        name="writing_tool",
                        arguments={
                            "command": "brainstorm_plans",
                            "request": request,
                            "plan_count": 3,
                        },
                    )
                )
                self.response_queue.put(
                    (
                        "brainstorm",
                        {
                            "success": tool_result.success,
                            "output": tool_result.output,
                            "plans": tool_result.meta.get("plans", []),
                        },
                    )
                )
                return

            if action == "create_from_plan":
                plan = payload["plan"]
                filename = str(payload.get("filename", "")).strip() or plan.get("filename", "article_from_plan.md")
                tool_result = self.agent.registry.execute(
                    ToolCall(
                        name="writing_tool",
                        arguments={
                            "command": "create",
                            "topic": plan.get("topic", "未命名主题"),
                            "style": plan.get("style", "通用"),
                            "word_count": int(plan.get("word_count", 600)),
                            "filename": filename,
                            "output_dir": str(payload.get("output_dir", ".")),
                            "custom_prompt": str(payload.get("custom_prompt", "")).strip(),
                            "api_provider": str(payload.get("api_provider", "mock")),
                            "api_model": str(payload.get("api_model", "")),
                            "api_key": str(payload.get("api_key", "")),
                            "api_base_url": str(payload.get("api_base_url", "")),
                        },
                    )
                )
                self.response_queue.put(
                    (
                        "create_from_plan",
                        {
                            "success": tool_result.success,
                            "output": tool_result.output,
                            "file_path": tool_result.meta.get("file_path", ""),
                        },
                    )
                )
                return

            if action == "preview_plan":
                plan = payload["plan"]
                tool_result = self.agent.registry.execute(
                    ToolCall(
                        name="writing_tool",
                        arguments={
                            "command": "preview_plan_content",
                            "topic": plan.get("topic", "未命名主题"),
                            "style": plan.get("style", "通用"),
                            "word_count": int(plan.get("word_count", 700)),
                            "custom_prompt": str(payload.get("custom_prompt", "")).strip(),
                            "api_provider": str(payload.get("api_provider", "mock")),
                            "api_model": str(payload.get("api_model", "")),
                            "api_key": str(payload.get("api_key", "")),
                            "api_base_url": str(payload.get("api_base_url", "")),
                        },
                    )
                )
                self.response_queue.put(
                    (
                        "preview_plan",
                        {
                            "index": int(payload.get("index", -1)),
                            "success": tool_result.success,
                            "output": tool_result.output,
                            "content": str(tool_result.meta.get("content", "")),
                        },
                    )
                )
                return

            if action == "create_direct":
                raw_word_count = payload.get("word_count")
                args: dict[str, Any] = {
                    "command": "create",
                    "topic": payload["topic"],
                    "style": "通用",
                    "word_count": int(raw_word_count) if raw_word_count is not None and str(raw_word_count).strip() else 1200,
                    "output_dir": payload["output_dir"],
                    "custom_prompt": str(payload.get("custom_prompt", "")).strip(),
                    "api_provider": str(payload.get("api_provider", "mock")),
                    "api_model": str(payload.get("api_model", "")),
                    "api_key": str(payload.get("api_key", "")),
                    "api_base_url": str(payload.get("api_base_url", "")),
                }
                filename = str(payload.get("filename", "")).strip()
                if filename:
                    args["filename"] = filename

                tool_result = self.agent.registry.execute(ToolCall(name="writing_tool", arguments=args))
                self.response_queue.put(
                    (
                        "create_direct",
                        {
                            "success": tool_result.success,
                            "output": tool_result.output,
                            "file_path": tool_result.meta.get("file_path", ""),
                        },
                    )
                )
                return

            if action == "draft_followup":
                file_path = str(payload.get("file_path", ""))
                instruction = str(payload.get("instruction", "")).strip()
                if not file_path or not instruction:
                    self.response_queue.put(("tool_generic", {"output": "后续补充缺少 file_path 或 instruction。"}))
                    return
                preview_result = self.agent.registry.execute(
                    ToolCall(
                        name="writing_tool",
                        arguments={
                            "command": "preview_edit",
                            "file_path": file_path,
                            "instruction": instruction,
                            "api_provider": str(payload.get("api_provider", "mock")),
                            "api_model": str(payload.get("api_model", "")),
                            "api_key": str(payload.get("api_key", "")),
                            "api_base_url": str(payload.get("api_base_url", "")),
                        },
                    )
                )
                if preview_result.success:
                    commit_result = self.agent.registry.execute(
                        ToolCall(name="writing_tool", arguments={"command": "commit_edit", "file_path": file_path})
                    )
                    output = preview_result.output + ("\n" + commit_result.output if commit_result.output else "")
                else:
                    output = preview_result.output
                self.response_queue.put(("draft_followup", {"output": output, "file_path": file_path, "success": preview_result.success}))
                return

            if action == "qq_configure":
                result = self.agent.registry.execute(
                    ToolCall(
                        name="qq_auto_reply",
                        arguments={
                            "command": "configure",
                            "enabled": payload.get("enabled", True),
                            "private_enabled": payload.get("private_enabled", True),
                            "target_group_id": payload["target_group_id"],
                            "target_group_ids": payload.get("target_group_ids", []),
                            "private_delay_sec": payload.get("private_delay_sec", 0),
                            "custom_prompt": payload["custom_prompt"],
                            "cooldown_sec": payload.get("cooldown_sec", 0),
                            "self_user_id": payload.get("self_user_id", "self_user"),
                            "gateway_mode": payload.get("gateway_mode", "managed"),
                            "managed_account": payload.get("managed_account", ""),
                            "managed_api_base_url": payload.get("managed_api_base_url", ""),
                            "managed_access_token": payload.get("managed_access_token", ""),
                            "reply_api_provider": payload.get("api_provider", "mock"),
                            "reply_api_model": payload.get("api_model", ""),
                            "reply_api_key": payload.get("api_key", ""),
                            "reply_api_base_url": payload.get("api_base_url", ""),
                        },
                    )
                )
                self.response_queue.put(("tool_generic", {"output": result.output, "status": result.meta, "success": result.success}))
                return

            if action == "qq_group_add":
                result = self.agent.registry.execute(
                    ToolCall(
                        name="qq_auto_reply",
                        arguments={"command": "add_target_group", "group_id": payload.get("group_id", "")},
                    )
                )
                self.response_queue.put(("tool_generic", {"output": result.output, "status": result.meta, "success": result.success, "kind": "qq_group_mgmt"}))
                return

            if action == "qq_group_remove":
                result = self.agent.registry.execute(
                    ToolCall(
                        name="qq_auto_reply",
                        arguments={"command": "remove_target_group", "group_id": payload.get("group_id", "")},
                    )
                )
                self.response_queue.put(("tool_generic", {"output": result.output, "status": result.meta, "success": result.success, "kind": "qq_group_mgmt"}))
                return

            if action == "qq_group_update":
                result = self.agent.registry.execute(
                    ToolCall(
                        name="qq_auto_reply",
                        arguments={
                            "command": "update_target_group",
                            "old_group_id": payload.get("old_group_id", ""),
                            "new_group_id": payload.get("new_group_id", ""),
                        },
                    )
                )
                self.response_queue.put(("tool_generic", {"output": result.output, "status": result.meta, "success": result.success, "kind": "qq_group_mgmt"}))
                return

            if action == "qq_bind_local_client_auto":
                result = self.agent.registry.execute(
                    ToolCall(
                        name="qq_auto_reply",
                        arguments={
                            "command": "bind_local_client_auto",
                            "gateway_mode": payload.get("gateway_mode", "windows"),
                            "connect_now": payload.get("connect_now", True),
                        },
                    )
                )
                self.response_queue.put(("tool_generic", {"output": result.output, "status": result.meta, "success": result.success, "kind": "qq_bind"}))
                return

            if action == "qq_bootstrap":
                result = self.agent.registry.execute(
                    ToolCall(
                        name="qq_auto_reply",
                        arguments={
                            "command": "bootstrap",
                            "gateway_mode": payload.get("gateway_mode", "managed"),
                            "connect_now": payload.get("connect_now", True),
                            "managed_account": payload.get("managed_account", ""),
                            "managed_api_base_url": payload.get("managed_api_base_url", ""),
                            "managed_access_token": payload.get("managed_access_token", ""),
                            "search_roots": payload.get("search_roots", []),
                        },
                    )
                )
                self.response_queue.put(("tool_generic", {"output": result.output, "status": result.meta, "success": result.success, "kind": "qq_bootstrap"}))
                return

            if action == "qq_download_napcat":
                result = self.agent.registry.execute(ToolCall(name="qq_auto_reply", arguments={"command": "download_napcat"}))
                self.response_queue.put(("tool_generic", {"output": result.output, "status": result.meta, "success": result.success, "kind": "qq_download"}))
                return

            if action == "qq_status":
                result = self.agent.registry.execute(ToolCall(name="qq_auto_reply", arguments={"command": "get_status"}))
                self.response_queue.put(("tool_generic", {"output": result.output, "status": result.meta, "success": result.success, "kind": "qq_status"}))
                return

            if action == "qq_poll_pending":
                result = self.agent.registry.execute(ToolCall(name="qq_auto_reply", arguments={"command": "poll_pending"}))
                self.response_queue.put(("tool_generic", {"output": result.output}))
                return

            if action == "qq_simulate":
                source = payload["source"]
                args = {
                    "command": "handle_message",
                    "source": source,
                    "chat_id": payload["chat_id"],
                    "sender_id": payload["sender_id"],
                    "text": payload["text"],
                }
                if source == "group":
                    args["mentioned"] = True
                    args["mention_all"] = False
                else:
                    args["waited_sec"] = int(payload.get("waited_sec", 0) or 0)
                args.update(
                    {
                        "reply_api_provider": payload.get("api_provider", "mock"),
                        "reply_api_model": payload.get("api_model", ""),
                        "reply_api_key": payload.get("api_key", ""),
                        "reply_api_base_url": payload.get("api_base_url", ""),
                    }
                )
                result = self.agent.registry.execute(ToolCall(name="qq_auto_reply", arguments=args))
                self.response_queue.put(("tool_generic", {"output": result.output, "success": result.success, "kind": "qq_simulate"}))
                return

            if action == "qq_user_replied":
                result = self.agent.registry.execute(
                    ToolCall(name="qq_auto_reply", arguments={"command": "user_replied", "chat_id": payload["chat_id"]})
                )
                self.response_queue.put(("tool_generic", {"output": result.output}))
                return

            if action == "image_process":
                result = self.agent.registry.execute(
                    ToolCall(
                        name="image_batch_tool",
                        arguments={
                            "command": "process",
                            "input_dir": payload["input_dir"],
                            "output_dir": payload["output_dir"],
                            "target_format": payload["target_format"],
                            "width": payload["width"],
                            "height": payload["height"],
                            "keep_ratio": payload["keep_ratio"],
                            "overwrite": payload["overwrite"],
                            "confirm_lossy": payload["confirm_lossy"],
                            "start_index": payload["start_index"],
                            "pad_width": payload["pad_width"],
                            "pattern": payload["pattern"],
                            "per_image_timeout_sec": payload["per_image_timeout_sec"],
                            "request": payload.get("request", ""),
                        },
                    )
                )
                task_id = str(result.meta.get("task_id", ""))
                self.response_queue.put(("image_process", {"output": result.output, "task_id": task_id}))
                return

            if action == "image_status":
                result = self.agent.registry.execute(
                    ToolCall(name="image_batch_tool", arguments={"command": "task_status", "task_id": payload["task_id"]})
                )
                self.response_queue.put(("tool_generic", {"output": result.output}))
                return

            if action == "image_cancel":
                result = self.agent.registry.execute(
                    ToolCall(name="image_batch_tool", arguments={"command": "cancel_task", "task_id": payload["task_id"]})
                )
                self.response_queue.put(("tool_generic", {"output": result.output}))
                return

        except Exception as exc:  # noqa: BLE001
            self.response_queue.put(("error", {"message": str(exc)}))

    def _poll_queue(self) -> None:
        """轮询后台结果。"""
        try:
            while True:
                action, payload = self.response_queue.get_nowait()
                if action == "agent_message":
                    traces = payload.get("traces", [])
                    if self.show_trace_var.get():
                        for line in traces:
                            self._append_trace(line)
                    self._append_chat("Clawmini", str(payload.get("answer", "")), stream=self.stream_output_var.get())

                elif action == "brainstorm":
                    success = bool(payload.get("success", False))
                    output = str(payload.get("output", ""))
                    self._append_chat("Clawmini", output, stream=False)
                    if success:
                        plans = payload.get("plans", [])
                        self._refresh_plans(plans if isinstance(plans, list) else [])

                elif action == "create_from_plan":
                    self._append_chat("Clawmini", str(payload.get("output", "")), stream=False)
                    file_path = str(payload.get("file_path", ""))
                    if file_path:
                        self.current_preview_file = Path(file_path)
                        self._load_preview_file(self.current_preview_file)

                elif action == "preview_plan":
                    idx = int(payload.get("index", -1))
                    if 0 <= idx < len(self.last_plans):
                        self.last_plans[idx]["preview_content"] = str(payload.get("content", ""))
                        if self.selected_plan_index == idx:
                            self.on_show_selected_plan()

                elif action == "create_direct":
                    self._append_chat("Clawmini", str(payload.get("output", "")), stream=False)
                    file_path = str(payload.get("file_path", ""))
                    if file_path:
                        self.current_preview_file = Path(file_path)
                        self._load_preview_file(self.current_preview_file)
                        self.draft_followup_mode = True
                        self._append_chat("系统", "文稿已生成并预览完成，请在底部全局控制台输入后续补充内容。")

                elif action == "draft_followup":
                    self._append_chat("Clawmini", str(payload.get("output", "")), stream=False)
                    file_path = str(payload.get("file_path", ""))
                    if file_path:
                        self.current_preview_file = Path(file_path)
                        self._load_preview_file(self.current_preview_file)
                    self.draft_followup_mode = True
                    self._append_chat("系统", "后续补充已应用。若还需继续修改，可直接在底部全局控制台继续输入。")

                elif action == "image_process":
                    self._append_chat("Clawmini", str(payload.get("output", "")), stream=False)
                    task_id = str(payload.get("task_id", ""))
                    if task_id:
                        self.img_task_var.set(task_id)

                elif action == "qq_gateway_event":
                    raw_event = payload.get("payload") if isinstance(payload.get("payload"), dict) else payload
                    event_path = str(payload.get("path", ""))
                    raw_body = str(payload.get("raw_body", ""))
                    if raw_body:
                        self._append_chat("NapCat", f"收到事件：{event_path}\n原始包：{raw_body}", stream=False)
                    else:
                        self._append_chat("NapCat", f"收到事件：{event_path}", stream=False)
                    if event_path == "/qq/binding":
                        binding_text = "NapCat绑定反馈"
                        if isinstance(raw_event, dict):
                            binding_bits: list[str] = []
                            for key in ("connected", "app_title_keyword", "window_title", "process_name", "notes"):
                                value = raw_event.get(key)
                                if value not in (None, ""):
                                    binding_bits.append(f"{key}={value}")
                            if binding_bits:
                                binding_text = f"NapCat绑定反馈：{' | '.join(binding_bits)}"
                            else:
                                binding_text = f"NapCat绑定反馈：{json.dumps(raw_event, ensure_ascii=False)}"
                        else:
                            binding_text = f"NapCat绑定反馈：{raw_event}"
                        self._set_qq_status_message(binding_text)
                    else:
                        result = self.agent.registry.execute(ToolCall(name="qq_auto_reply", arguments={"command": "handle_gateway_event", "event": raw_event, "raw_body": raw_body}))
                        if isinstance(result.meta, dict):
                            self._sync_qq_ui_from_status(result.meta)
                        if result.success:
                            send_chat_id = str(result.meta.get("chat_id", "")) if isinstance(result.meta, dict) else ""
                            send_message_type = str(result.meta.get("message_type", "")) if isinstance(result.meta, dict) else ""
                            reply_text = str(result.meta.get("reply", "")) if isinstance(result.meta, dict) else ""
                            reply_source = str(result.meta.get("reply_source", "local")) if isinstance(result.meta, dict) else "local"
                            reply_api_error = str(result.meta.get("reply_api_error", "")) if isinstance(result.meta, dict) else ""
                            reply_api_endpoint = str(result.meta.get("reply_api_endpoint", "")) if isinstance(result.meta, dict) else ""
                            endpoint = str(result.meta.get("endpoint", "")) if isinstance(result.meta, dict) else ""
                            response_text = str(result.meta.get("response", "")) if isinstance(result.meta, dict) else ""
                            self._set_qq_status_message(f"NapCat事件已收到：{result.output}")
                            if reply_source and reply_source != "local":
                                self._append_chat("Clawmini", f"回复来源：{reply_source} | 接口：{reply_api_endpoint or '未返回'}", stream=False)
                            elif reply_api_error:
                                self._append_chat("Clawmini", f"回复API未接入：{reply_api_error}", stream=False)
                            if send_chat_id or reply_text or endpoint or response_text:
                                response_suffix = f"\n接口：{endpoint}" if endpoint else ""
                                response_suffix += f"\n回包：{response_text}" if response_text else ""
                                self._append_chat(
                                    "NapCat",
                                    f"成功：{result.output}\n发送目标：{send_message_type} / {send_chat_id}\n回复内容：{reply_text}{response_suffix}",
                                    stream=False,
                                )
                            else:
                                self._append_chat("NapCat", f"成功：{result.output}", stream=False)
                        else:
                            self._set_qq_status_message(f"NapCat事件处理失败：{result.output}")
                            if raw_body:
                                self._append_chat("NapCat", f"失败：{result.output}\n原始包：{raw_body}", stream=False)
                            else:
                                self._append_chat("NapCat", f"失败：{result.output}", stream=False)

                elif action == "tool_generic":
                    output = str(payload.get("output", ""))
                    if payload.get("success") is False:
                        self._set_qq_status_message(f"操作失败：{output}")
                    elif payload.get("kind") == "qq_simulate":
                        self._set_qq_status_message(f"消息模拟完成：{output}")
                    if "status" in payload and isinstance(payload.get("status"), dict):
                        status = payload["status"]
                        self._sync_qq_ui_from_status(status)
                        reply_api_provider = str(status.get("reply_api_provider", "")).strip().lower()
                        reply_api_model = str(status.get("reply_api_model", "")).strip()
                        reply_api_base_url = str(status.get("reply_api_base_url", "")).strip()
                        reply_api_key_state = "已配置" if str(status.get("reply_api_key", "")).strip() else "未配置"
                        if reply_api_provider and payload.get("kind") in {"qq_configure", "qq_simulate", "qq_status"}:
                            self._append_chat(
                                "Clawmini",
                                f"回复API状态：provider={reply_api_provider} model={reply_api_model or '默认'} base_url={reply_api_base_url or '默认'} key={reply_api_key_state}",
                                stream=False,
                            )
                        if payload.get("kind") == "qq_group_mgmt":
                            if status.get("target_group_id"):
                                self.qq_group_var.set(str(status.get("target_group_id")))
                            self._set_qq_status_message(f"群号列表已更新：{status.get('target_group_id')}")
                            self._append_chat("Clawmini", output, stream=False)
                            continue
                        if payload.get("kind") == "qq_bind":
                            bind_prefix = "NapCat绑定成功：" if bool(payload.get("success")) else "NapCat绑定失败："
                            binding = status.get("binding") if isinstance(status, dict) else None
                            binding_suffix = ""
                            if isinstance(binding, dict):
                                binding_suffix = f" | 绑定={binding.get('app_title_keyword')} connected={binding.get('connected')} window={binding.get('window_title')}"
                            if isinstance(binding, dict):
                                self._set_qq_status_message(
                                    bind_prefix
                                    + f"绑定={binding.get('app_title_keyword')} connected={binding.get('connected')} window={binding.get('window_title')}"
                                    + (f" | 备注={binding.get('notes')}" if binding.get('notes') else "")
                                )
                            else:
                                self._set_qq_status_message(bind_prefix + f"未拿到绑定详情：{output}")
                        elif payload.get("kind") == "qq_bootstrap":
                            if isinstance(status, dict):
                                binding = status.get("binding") if isinstance(status, dict) else None
                                if isinstance(binding, dict):
                                    status_text = (
                                        f"NapCat绑定成功：gateway={status.get('gateway_mode')} account={status.get('managed_account') or status.get('self_user_id')}"
                                        f" | api={status.get('managed_api_base_url') or ''}"
                                        f" | 绑定={binding.get('app_title_keyword')} connected={binding.get('connected')}"
                                        + (f" | 备注={binding.get('notes')}" if binding.get('notes') else "")
                                    )
                                    self._set_qq_status_message(status_text)
                                else:
                                    status_text = (
                                        f"NapCat绑定成功：gateway={status.get('gateway_mode')} account={status.get('managed_account') or status.get('self_user_id')}"
                                        f" | api={status.get('managed_api_base_url') or ''}"
                                    )
                                    self._set_qq_status_message(status_text)
                            else:
                                status_text = f"NapCat绑定成功：{output}"
                                self._set_qq_status_message(status_text)
                        elif payload.get("kind") == "qq_download":
                            if isinstance(status, dict) and status.get("url"):
                                status_text = f"已打开 NapCat 下载页：{status.get('url')}"
                                self._set_qq_status_message(status_text)
                            else:
                                status_text = f"已打开 NapCat 下载页：{output}"
                                self._set_qq_status_message(status_text)
                        else:
                            binding = status.get("binding") if isinstance(status, dict) else None
                            binding_suffix = ""
                            if isinstance(binding, dict):
                                binding_suffix = (
                                    f" | 绑定={binding.get('app_title_keyword')} connected={binding.get('connected')}"
                                    f" window={binding.get('window_title')}"
                                )
                            status_text = self._qq_status_text_from_status(status) + f"{binding_suffix}"
                            self._set_qq_status_message(status_text)
                        if payload.get("kind") == "qq_simulate":
                            reply_source = str(status.get("reply_source", "local")).strip()
                            reply_error = str(status.get("reply_api_error", "")).strip()
                            reply_endpoint = str(status.get("reply_api_endpoint", "")).strip()
                            if reply_source and reply_source != "local":
                                self._append_chat("NapCat", f"回复来源：{reply_source} | 接口：{reply_endpoint or '未返回'}", stream=False)
                            elif reply_error:
                                self._append_chat("NapCat", f"回复API未接入：{reply_error}", stream=False)
                    elif payload.get("success") is True and "配置已更新" in output:
                        token_state = "已配置" if self.qq_managed_token_var.get().strip() else "未配置"
                        status_text = (
                            f"配置已更新：group={self.qq_group_var.get().strip()} private_delay={self.qq_delay_var.get()}s cooldown={self.qq_cooldown_var.get()}s "
                            f"enabled={self.qq_enabled_var.get()} private={self.qq_private_enabled_var.get()} gateway={self.qq_gateway_var.get().strip()} token={token_state}"
                        )
                        self._set_qq_status_message(status_text)
                    if payload.get("kind") == "qq_simulate":
                        if payload.get("success") is False:
                            self._append_chat("NapCat", f"模拟发送失败：{output}", stream=False)
                        else:
                            self._append_chat("NapCat", f"模拟发送结果：{output}", stream=False)
                    self._append_chat("Clawmini", output, stream=False)

                elif action == "error":
                    self._append_chat("错误", str(payload.get("message", "未知异常")), stream=False)

        except queue.Empty:
            pass
        finally:
            self.root.after(120, self._poll_queue)

    def _append_chat(self, speaker: str, text: str, stream: bool = False) -> None:
        """向聊天框追加文本。"""
        prefix = f"[{speaker}] "
        self.chat_text.configure(state=tk.NORMAL)
        self.chat_text.insert(tk.END, prefix)
        if stream:
            for ch in text:
                self.chat_text.insert(tk.END, ch)
                self.chat_text.see(tk.END)
                self.chat_text.update_idletasks()
        else:
            self.chat_text.insert(tk.END, text)
        self.chat_text.insert(tk.END, "\n\n")
        self.chat_text.see(tk.END)
        self.chat_text.configure(state=tk.DISABLED)

    def _append_trace(self, line: str) -> None:
        """向轨迹框追加一行。"""
        self.trace_text.configure(state=tk.NORMAL)
        self.trace_text.insert(tk.END, f"{line}\n")
        self.trace_text.see(tk.END)
        self.trace_text.configure(state=tk.DISABLED)

    def _set_text(self, widget: ScrolledText, text: str) -> None:
        """覆盖文本控件内容。"""
        widget.configure(state=tk.NORMAL)
        widget.delete("1.0", tk.END)
        widget.insert("1.0", text)
        widget.configure(state=tk.DISABLED)

    def _refresh_plans(self, plans: list[dict[str, Any]]) -> None:
        """刷新方案卡片。"""
        self.last_plans = plans
        self.selected_plan_index = 0 if plans else None

        for idx in range(3):
            if idx < len(plans):
                plan = plans[idx]
                style = plan.get("style", "通用")
                words = plan.get("word_count", "?")
                topic = plan.get("topic", "未命名主题")
                rationale = plan.get("rationale", "")
                self.plan_card_vars[idx].set(
                    f"主题：{topic}\n风格：{style} | 字数：{words}\n说明：{rationale}"
                )
                self.plan_select_buttons[idx].configure(state=tk.NORMAL)
            else:
                self.plan_card_vars[idx].set(f"方案{idx + 1}：暂无数据")
                self.plan_select_buttons[idx].configure(state=tk.DISABLED)

        if self.selected_plan_index is not None:
            self.on_show_selected_plan()
        else:
            self._set_text(self.plan_detail, "尚未生成方案。")

    def _load_preview_file(self, file_path: Path) -> None:
        """加载文稿内容到预览面板。"""
        try:
            if not file_path.exists():
                self.preview_path_var.set(f"当前文件：{file_path}（不存在）")
                self._set_text(self.preview_text, "文件不存在，无法预览。")
                return
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            self.preview_path_var.set(f"当前文件：{file_path}")
            self._set_text(self.preview_text, content)
        except Exception as exc:  # noqa: BLE001
            self.preview_path_var.set("当前文件：读取失败")
            self._set_text(self.preview_text, f"读取预览失败：{exc}")


def main() -> None:
    """APP 主入口。"""
    root = tk.Tk()
    app = ClawminiDebugApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
