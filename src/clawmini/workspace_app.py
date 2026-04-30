"""工作区会话式文件操作应用。"""

from __future__ import annotations

import ctypes
import json
import os
import queue
import re
import shlex
import shutil
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlparse

import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
from tkinter.scrolledtext import ScrolledText

from clawmini.config import AgentConfig
from clawmini.core.agent import ClawminiAgent
from clawmini.storage.history_store import HistoryStore
from clawmini.tools.qq_auto_reply import QQAutoReplyTool
from clawmini.types import Message, ToolCall
from clawmini.ui_theme import apply_theme
from clawmini.adapters.qq_adapter import discover_napcat_http_config


STATE_FILE_NAME = "app_state.json"
SESSIONS_DIR_NAME = "sessions"

# system prompt 已由 ClawminiAgent 内部管理，此处不再定义



def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _ensure_text(value: Any) -> str:
    return str(value or "").strip()


def _move_to_recycle_bin(path: Path, workspace_dir: Path) -> None:
    if os.name != "nt":
        trash_dir = workspace_dir / ".recycle_bin"
        trash_dir.mkdir(parents=True, exist_ok=True)
        target = trash_dir / path.name
        if target.exists():
            suffix = 1
            while (trash_dir / f"{path.stem}_{suffix}{path.suffix}").exists():
                suffix += 1
            target = trash_dir / f"{path.stem}_{suffix}{path.suffix}"
        shutil.move(str(path), str(target))
        return

    from ctypes import wintypes

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [
            ("hwnd", wintypes.HWND),
            ("wFunc", wintypes.UINT),
            ("pFrom", wintypes.LPCWSTR),
            ("pTo", wintypes.LPCWSTR),
            ("fFlags", wintypes.WORD),
            ("fAnyOperationsAborted", wintypes.BOOL),
            ("hNameMappings", wintypes.LPVOID),
            ("lpszProgressTitle", wintypes.LPCWSTR),
        ]

    FO_DELETE = 3
    FOF_ALLOWUNDO = 0x0040
    FOF_NOCONFIRMATION = 0x0010
    FOF_SILENT = 0x0004
    FOF_NOERRORUI = 0x0400

    path_buffer = ctypes.create_unicode_buffer(str(path) + "\0\0")
    operation = SHFILEOPSTRUCTW()
    operation.hwnd = None
    operation.wFunc = FO_DELETE
    operation.pFrom = ctypes.cast(path_buffer, wintypes.LPCWSTR)
    operation.pTo = None
    operation.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT | FOF_NOERRORUI
    operation.fAnyOperationsAborted = False
    operation.hNameMappings = None
    operation.lpszProgressTitle = None
    result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(operation))
    if result != 0:
        raise OSError(f"回收站删除失败，错误码={result}")
    if operation.fAnyOperationsAborted:
        raise OSError("回收站删除已中止")


@dataclass(slots=True)
class WorkspaceSession:
    session_id: str
    title: str
    history_path: Path
    created_at: str
    updated_at: str
    agent: ClawminiAgent

    @property
    def message_count(self) -> int:
        return len(self.agent.memory.messages)


class WorkspaceSessionManager:
    def __init__(self, workspace_dir: Path) -> None:
        self.workspace_dir = workspace_dir
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        self.state_path = self.workspace_dir / STATE_FILE_NAME
        self.sessions_dir = self.workspace_dir / SESSIONS_DIR_NAME
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

        self.settings: dict[str, Any] = self._default_settings()
        self.active_session_id: str | None = None
        self.sessions: dict[str, WorkspaceSession] = {}
        self._load_state()

    def _default_settings(self) -> dict[str, Any]:
        return {
            "model_provider": "mock",
            "model_name": "clawmini-mock",
            "api_key": "",
            "base_url": "",
            "port": 17888,
            "enable_search": False,
            "provider_configs": {
                "deepseek": {"model_name": "deepseek-chat", "api_key": "", "base_url": "https://api.deepseek.com"},
                "openai": {"model_name": "gpt-4o", "api_key": "", "base_url": "https://api.openai.com/v1"},
                "qwen": {"model_name": "qwen-plus", "api_key": "", "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1"},
                "mock": {"model_name": "clawmini-mock", "api_key": "", "base_url": ""},
            },
        }

    def _session_history_path(self, session_id: str) -> Path:
        return self.sessions_dir / f"{session_id}.json"

    def _build_agent(self, history_path: Path) -> ClawminiAgent:
        provider = str(self.settings.get("model_provider", "mock")).strip().lower() or "mock"
        provider_cfgs = self.settings.get("provider_configs", {})
        pcfg = provider_cfgs.get(provider, {})
        config = AgentConfig(
            model_provider=provider,
            model_name=str(self.settings.get("model_name", pcfg.get("model_name", "clawmini-mock"))).strip() or "clawmini-mock",
            api_key=str(self.settings.get("api_key", pcfg.get("api_key", ""))).strip() or None,
            base_url=str(self.settings.get("base_url", pcfg.get("base_url", ""))).strip() or None,
            workspace_dir=self.workspace_dir,
            history_path=history_path,
            max_rounds=6,
            show_react_steps=True,
            enable_stream_output=True,
            enable_search=self.settings.get("enable_search", False),
        )
        return ClawminiAgent(config, session_manager=self)

    # _seed_system_prompt 不再需要，agent 内部管理 system prompt

    def _new_session_id(self) -> str:
        return f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

    def _default_title(self) -> str:
        return f"会话 {len(self.sessions) + 1}"

    def _load_state(self) -> None:
        if not self.state_path.exists():
            self.create_session()
            self.save_state()
            return

        try:
            raw = json.loads(self.state_path.read_text(encoding="utf-8"))
        except Exception:
            self.create_session()
            self.save_state()
            return

        settings = raw.get("settings", {}) if isinstance(raw, dict) else {}
        if isinstance(settings, dict):
            self.settings.update(settings)
        self.active_session_id = _ensure_text(raw.get("active_session_id")) or None

        sessions = raw.get("sessions", []) if isinstance(raw, dict) else []
        if isinstance(sessions, list) and sessions:
            for item in sessions:
                if not isinstance(item, dict):
                    continue
                session_id = _ensure_text(item.get("session_id"))
                if not session_id:
                    continue
                title = _ensure_text(item.get("title")) or self._default_title()
                history_rel = _ensure_text(item.get("history_file"))
                history_path = self.workspace_dir / history_rel if history_rel else self._session_history_path(session_id)
                session = WorkspaceSession(
                    session_id=session_id,
                    title=title,
                    history_path=history_path,
                    created_at=_ensure_text(item.get("created_at")) or _now_iso(),
                    updated_at=_ensure_text(item.get("updated_at")) or _now_iso(),
                    agent=self._build_agent(history_path),
                )
                self.sessions[session_id] = session

        if not self.sessions:
            self.create_session()

        if self.active_session_id not in self.sessions:
            self.active_session_id = next(iter(self.sessions))

    def save_state(self) -> None:
        payload = {
            "settings": self.settings,
            "active_session_id": self.active_session_id,
            "sessions": [
                {
                    "session_id": session.session_id,
                    "title": session.title,
                    "history_file": str(session.history_path.relative_to(self.workspace_dir)),
                    "created_at": session.created_at,
                    "updated_at": session.updated_at,
                    "message_count": session.message_count,
                }
                for session in sorted(self.sessions.values(), key=lambda item: item.updated_at, reverse=True)
            ],
        }
        self.state_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def create_session(self, title: str | None = None) -> WorkspaceSession:
        session_id = self._new_session_id()
        history_path = self._session_history_path(session_id)
        session = WorkspaceSession(
            session_id=session_id,
            title=(title or self._default_title()).strip() or self._default_title(),
            history_path=history_path,
            created_at=_now_iso(),
            updated_at=_now_iso(),
            agent=self._build_agent(history_path),
        )
        # agent 构造函数已注入 system prompt
        self.sessions[session_id] = session
        self.active_session_id = session_id
        self.save_state()
        return session

    def delete_session(self, session_id: str) -> tuple[bool, str]:
        session = self.sessions.get(session_id)
        if session is None:
            return False, f"会话不存在：{session_id}"
        try:
            if session.history_path.exists():
                _move_to_recycle_bin(session.history_path, self.workspace_dir)
        except Exception as exc:  # noqa: BLE001
            return False, f"删除会话历史失败：{exc}"
        self.sessions.pop(session_id, None)
        if self.active_session_id == session_id:
            self.active_session_id = next(iter(self.sessions), None)
        if not self.sessions:
            self.create_session()
        self.save_state()
        return True, f"已删除会话：{session_id}"

    def rename_session(self, session_id: str, title: str) -> tuple[bool, str]:
        session = self.sessions.get(session_id)
        if session is None:
            return False, f"会话不存在：{session_id}"
        new_title = title.strip()
        if not new_title:
            return False, "标题不能为空。"
        session.title = new_title
        session.updated_at = _now_iso()
        self.save_state()
        return True, f"已重命名会话：{session_id} -> {new_title}"

    def active_session(self) -> WorkspaceSession:
        if self.active_session_id and self.active_session_id in self.sessions:
            return self.sessions[self.active_session_id]
        return next(iter(self.sessions.values()))

    def set_active_session(self, session_id: str) -> tuple[bool, str]:
        if session_id not in self.sessions:
            return False, f"会话不存在：{session_id}"
        self.active_session_id = session_id
        self.save_state()
        return True, f"已切换到会话：{self.sessions[session_id].title}"

    def list_sessions(self) -> list[WorkspaceSession]:
        return sorted(self.sessions.values(), key=lambda item: item.updated_at, reverse=True)

    def update_settings(self, new_settings: dict[str, Any]) -> None:
        self.settings.update({k: v for k, v in new_settings.items() if v is not None})
        self.settings["port"] = int(self.settings.get("port", 17888))
        # 将当前 provider 的配置同步到 provider_configs
        provider = str(self.settings.get("model_provider", "mock")).strip().lower() or "mock"
        provider_cfgs = self.settings.setdefault("provider_configs", {})
        pcfg = provider_cfgs.setdefault(provider, {})
        pcfg["model_name"] = str(self.settings.get("model_name", pcfg.get("model_name", ""))).strip()
        pcfg["api_key"] = str(self.settings.get("api_key", pcfg.get("api_key", ""))).strip()
        pcfg["base_url"] = str(self.settings.get("base_url", pcfg.get("base_url", ""))).strip()
        provider_cfgs[provider] = pcfg
        for session in self.sessions.values():
            history_messages = list(session.agent.memory.messages)
            session.agent = self._build_agent(session.history_path)
            session.agent.memory.messages = history_messages or session.agent.memory.messages
            # agent 构造函数已注入 system prompt
            session.updated_at = _now_iso()
        self.save_state()


class QQAutoReplyPanel:
    STATE_FILE_NAME = "qq_ui_state.json"

    def __init__(self, parent: ttk.Frame, workspace_dir: Path) -> None:
        self.parent = parent
        self.workspace_dir = workspace_dir
        self.tool = QQAutoReplyTool(workspace_dir=workspace_dir)
        self.state_path = self.workspace_dir / self.STATE_FILE_NAME
        self._loading_state = False
        self._save_pending = False

        self.root_frame = ttk.Frame(parent)
        self.root_frame.grid(row=0, column=0, sticky="nsew")
        self.root_frame.grid_rowconfigure(0, weight=1)
        self.root_frame.grid_columnconfigure(0, weight=1)

        self.qq_status_text = tk.StringVar(value="状态：未查询。建议先看「操作指引」，再点「一键启动/填充」。")
        self.qq_webhook_url_var = tk.StringVar(value="NapCat事件接收地址：未启动")

        self.text_api_provider_var = tk.StringVar(value="deepseek")
        self.text_api_model_var = tk.StringVar(value="deepseek-chat")
        self.text_api_key_var = tk.StringVar(value="")
        self.text_api_base_url_var = tk.StringVar(value="https://api.deepseek.com")

        self.qq_group_var = tk.StringVar(value="demo_chat")
        self.qq_delay_var = tk.IntVar(value=0)
        self.qq_cooldown_var = tk.IntVar(value=0)
        self.qq_self_user_var = tk.StringVar(value="self_user")
        self.qq_group_edit_var = tk.StringVar(value="")
        self.qq_group_new_var = tk.StringVar(value="")
        self.qq_private_enabled_var = tk.BooleanVar(value=True)
        self.qq_enabled_var = tk.BooleanVar(value=True)
        self.qq_gateway_var = tk.StringVar(value="managed")
        self.qq_connect_now_var = tk.BooleanVar(value=True)
        self.qq_prompt_var = tk.StringVar(value="")
        self.qq_managed_api_base_var = tk.StringVar(value="http://127.0.0.1:6099/plugin/napcat-plugin-builtin/api")
        self.qq_managed_token_var = tk.StringVar(value="")
        self.qq_receive_token_var = tk.StringVar(value="")
        self.qq_managed_account_var = tk.StringVar(value="3892874358")
        self.qq_image_recognition_var = tk.BooleanVar(value=True)
        self.qq_source_var = tk.StringVar(value="private")
        self.qq_chat_var = tk.StringVar(value="demo_chat")
        self.qq_sender_var = tk.StringVar(value="user_001")
        self.qq_waited_sec_var = tk.IntVar(value=0)
        self.qq_text_var = tk.StringVar(value="你好，请帮我回复")

        self._build_ui()
        self._wire_state_persistence()
        self._restore_from_tool_status()
        self._load_state()

    def _build_ui(self) -> None:
        # root_frame: 左(会话区) + 右(配置区) — 右宽左窄，自适应
        self.root_frame.grid_columnconfigure(0, weight=2, minsize=280)
        self.root_frame.grid_columnconfigure(1, weight=3, minsize=360)
        self.root_frame.grid_rowconfigure(0, weight=1)

        # ── 右半部分：配置（可滚动） ──
        config_frame = ttk.Frame(self.root_frame)
        config_frame.grid(row=0, column=1, sticky="nsew", padx=(4, 2))
        config_frame.grid_rowconfigure(0, weight=1)
        config_frame.grid_columnconfigure(0, weight=1)
        config_canvas = tk.Canvas(config_frame, highlightthickness=0)
        config_scroll = ttk.Scrollbar(config_frame, orient=tk.VERTICAL, command=config_canvas.yview)
        body = ttk.Frame(config_canvas)
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
        # 鼠标滚轮支持
        def _on_cfg_mousewheel(event: tk.Event[Any]) -> None:
            config_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        config_canvas.bind("<Enter>", lambda e: config_canvas.bind_all("<MouseWheel>", _on_cfg_mousewheel, add="+"))
        config_canvas.bind("<Leave>", lambda e: config_canvas.unbind_all("<MouseWheel>"))

        ttk.Label(body, text="QQ自动回复（独立页）", font=("Microsoft YaHei UI", 10, "bold")).pack(anchor=tk.W)

        guide = ttk.LabelFrame(body, text="操作指引", padding=8)
        guide.pack(fill=tk.X, pady=(8, 6))
        guide_text = (
            "1. 先选网关：测试选 mock，正式用 managed。\n"
            "2. 下载安装 NapCat：点下方「下载NapCat」按钮从官网获取。\n"
            "3. 安装后点「一键启动/填充」，自动识别账号和地址。\n"
            "4. 再点「更新配置」保存群号、延时等设置。\n"
            "5. 先用「模拟收到消息」测试回复效果，再切换到真实 QQ。\n"
            "6. 如果提示缺少 pywinauto，在终端执行：python -m pip install pywinauto"
        )
        ttk.Label(guide, text=guide_text, justify=tk.LEFT, foreground="#444").pack(anchor=tk.W)

        api_box = ttk.LabelFrame(body, text="文本 API（QQ 独立配置）", padding=8)
        api_box.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(api_box, text="Provider:").grid(row=0, column=0, sticky=tk.W)
        ttk.Combobox(api_box, textvariable=self.text_api_provider_var, values=["openai", "deepseek", "qwen", "mock"], width=10, state="readonly").grid(row=0, column=1, sticky=tk.W, padx=4)
        ttk.Label(api_box, text="Model:").grid(row=0, column=2, sticky=tk.W, padx=(8, 0))
        ttk.Entry(api_box, textvariable=self.text_api_model_var, width=16).grid(row=0, column=3, sticky=tk.W, padx=4)
        ttk.Label(api_box, text="API Key:").grid(row=1, column=0, sticky=tk.W, pady=(4, 0))
        ttk.Entry(api_box, textvariable=self.text_api_key_var, width=22).grid(row=1, column=1, sticky=tk.W, padx=4, pady=(4, 0))
        ttk.Label(api_box, text="Base URL:").grid(row=1, column=2, sticky=tk.W, pady=(4, 0), padx=(8, 0))
        ttk.Entry(api_box, textvariable=self.text_api_base_url_var, width=28).grid(row=1, column=3, sticky=tk.W, padx=4, pady=(4, 0))
        self.search_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(api_box, text="联网搜索 🔍（DeepSeek/Qwen 可用）", variable=self.search_var).grid(row=2, column=0, columnspan=4, sticky=tk.W, pady=(6, 0))

        cfg = ttk.Frame(body)
        cfg.pack(fill=tk.X, pady=(8, 6))
        ttk.Label(cfg, text="基础配置", font=("Microsoft YaHei UI", 10, "bold")).grid(row=0, column=0, columnspan=6, sticky=tk.W, pady=(0, 6))
        ttk.Label(cfg, text="目标群号(可多个，逗号分隔):").grid(row=1, column=0, sticky=tk.W)
        ttk.Entry(cfg, textvariable=self.qq_group_var, width=24).grid(row=1, column=1, padx=6)
        ttk.Label(cfg, text="私聊延时(秒):").grid(row=1, column=2, sticky=tk.W)
        ttk.Entry(cfg, textvariable=self.qq_delay_var, width=10).grid(row=1, column=3, padx=6)
        ttk.Label(cfg, text="冷却(秒):").grid(row=1, column=4, sticky=tk.W)
        ttk.Entry(cfg, textvariable=self.qq_cooldown_var, width=8).grid(row=1, column=5, padx=6)

        ttk.Label(cfg, text="当前账号ID:").grid(row=2, column=0, sticky=tk.W, pady=(8, 0))
        ttk.Entry(cfg, textvariable=self.qq_self_user_var, width=12).grid(row=2, column=1, padx=6, pady=(8, 0))
        ttk.Checkbutton(cfg, text="启用私聊回复", variable=self.qq_private_enabled_var).grid(row=2, column=2, sticky=tk.W, pady=(8, 0), padx=(4,0))
        ttk.Checkbutton(cfg, text="启用自动回复", variable=self.qq_enabled_var).grid(row=2, column=3, sticky=tk.W, pady=(8, 0), padx=(4,0))
        ttk.Label(cfg, text="网关:").grid(row=2, column=4, sticky=tk.W, pady=(8, 0), padx=(8,0))
        ttk.Combobox(cfg, textvariable=self.qq_gateway_var, values=["mock", "managed", "windows"], width=8, state="readonly").grid(row=2, column=5, padx=4, pady=(8, 0))

        ttk.Checkbutton(cfg, text="连接后立即尝试发送", variable=self.qq_connect_now_var).grid(row=3, column=0, columnspan=2, sticky=tk.W, pady=(6, 0))

        ttk.Label(cfg, text="群号管理:").grid(row=4, column=0, sticky=tk.W, pady=(6, 0))
        ttk.Entry(cfg, textvariable=self.qq_group_edit_var, width=12).grid(row=4, column=1, padx=4, pady=(6, 0), sticky=tk.W)
        ttk.Button(cfg, text="新增", command=self.on_qq_group_add).grid(row=4, column=2, sticky=tk.W, pady=(6, 0))
        ttk.Button(cfg, text="删除", command=self.on_qq_group_remove).grid(row=4, column=3, sticky=tk.W, pady=(6, 0), padx=(4,0))
        ttk.Label(cfg, text="新群号:").grid(row=5, column=0, sticky=tk.W, pady=(6, 0))
        ttk.Entry(cfg, textvariable=self.qq_group_new_var, width=12).grid(row=5, column=1, padx=4, pady=(6, 0), sticky=tk.W)
        ttk.Button(cfg, text="修改", command=self.on_qq_group_update).grid(row=5, column=2, sticky=tk.W, pady=(6, 0))

        ttk.Label(cfg, text="自定义提示词:").grid(row=6, column=0, sticky=tk.W, pady=(8, 0))
        ttk.Entry(cfg, textvariable=self.qq_prompt_var, width=36).grid(row=6, column=1, columnspan=5, sticky=tk.W, pady=(8, 0))

        managed_row = ttk.LabelFrame(body, text="managed / NapCat 在线发送", padding=8)
        managed_row.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(managed_row, text="API 基址:").grid(row=0, column=0, sticky=tk.W)
        ttk.Entry(managed_row, textvariable=self.qq_managed_api_base_var, width=42).grid(row=0, column=1, columnspan=3, sticky=tk.W, padx=6)
        ttk.Label(managed_row, text="发送Token(必填):").grid(row=1, column=0, sticky=tk.W, pady=(4, 0))
        ttk.Entry(managed_row, textvariable=self.qq_managed_token_var, width=22).grid(row=1, column=1, sticky=tk.W, padx=4, pady=(4, 0))
        ttk.Label(managed_row, text="接收Token(可选):").grid(row=1, column=2, sticky=tk.W, pady=(4, 0), padx=(8, 0))
        ttk.Entry(managed_row, textvariable=self.qq_receive_token_var, width=22).grid(row=1, column=3, sticky=tk.W, padx=4, pady=(4, 0))
        ttk.Label(managed_row, text="账号ID:").grid(row=2, column=0, sticky=tk.W, pady=(4, 0))
        ttk.Entry(managed_row, textvariable=self.qq_managed_account_var, width=14).grid(row=2, column=1, sticky=tk.W, padx=4, pady=(4, 0))
        ttk.Label(managed_row, text="💡 发送Token→发消息用；接收Token→验证事件。一键启动可自动识别。", foreground="#666").grid(row=3, column=0, columnspan=4, sticky=tk.W, pady=(4, 0))

        actions = ttk.Frame(body)
        actions.pack(fill=tk.X, pady=6)
        ttk.Label(actions, text="快捷操作:", foreground="#444").grid(row=0, column=0, sticky=tk.W, padx=(0, 4), pady=(0, 4))
        ttk.Button(actions, text="下载NapCat", command=self.on_qq_download_napcat).grid(row=0, column=1, sticky=tk.W, padx=(0, 4), pady=(0, 4))
        ttk.Button(actions, text="一键启动/填充", command=self.on_qq_bootstrap).grid(row=0, column=2, sticky=tk.W, padx=(0, 4), pady=(0, 4))
        ttk.Button(actions, text="更新配置", command=self.on_qq_configure).grid(row=0, column=3, sticky=tk.W, padx=(0, 4), pady=(0, 4))
        ttk.Button(actions, text="一键绑定客户端", command=self.on_qq_bind_local_client_auto).grid(row=1, column=0, sticky=tk.W, padx=(0, 4))
        ttk.Button(actions, text="查询状态", command=self.on_qq_status).grid(row=1, column=1, sticky=tk.W, padx=(0, 4))
        ttk.Button(actions, text="轮询待回复", command=self.on_qq_poll_pending).grid(row=1, column=2, sticky=tk.W, padx=(0, 4))
        ttk.Button(actions, text="暂停", command=self.on_qq_pause).grid(row=1, column=3, sticky=tk.W, padx=(0, 4))
        ttk.Button(actions, text="恢复", command=self.on_qq_resume).grid(row=2, column=0, sticky=tk.W, padx=(0, 4), pady=(4, 0))
        ttk.Button(actions, text="重启事件服务器", command=self.on_qq_restart_webhook).grid(row=2, column=1, sticky=tk.W, padx=(0, 4), pady=(4, 0))

        simulate = ttk.LabelFrame(body, text="消息模拟", padding=8)
        simulate.pack(fill=tk.X, pady=8)
        ttk.Label(simulate, text="先模拟测试，确认回复正常后再切换到真实 QQ。", foreground="#666").grid(row=0, column=0, columnspan=4, sticky=tk.W, pady=(0, 4))
        ttk.Label(simulate, text="消息来源:").grid(row=1, column=0, sticky=tk.W)
        ttk.Combobox(simulate, textvariable=self.qq_source_var, values=["private", "group"], width=8, state="readonly").grid(row=1, column=1, sticky=tk.W)
        ttk.Label(simulate, text="会话ID:").grid(row=1, column=2, sticky=tk.W, padx=(8, 0))
        ttk.Entry(simulate, textvariable=self.qq_chat_var, width=20).grid(row=1, column=3, padx=4)
        ttk.Button(simulate, text="模拟收到消息", command=self.on_qq_simulate_message).grid(row=1, column=4, rowspan=3, padx=(8, 4), sticky=tk.NS)
        ttk.Button(simulate, text="模拟用户手动回复(取消)", command=self.on_qq_manual_replied).grid(row=1, column=5, rowspan=3, padx=4, sticky=tk.NS)
        ttk.Label(simulate, text="发送者ID:").grid(row=2, column=0, sticky=tk.W, pady=(4, 0))
        ttk.Entry(simulate, textvariable=self.qq_sender_var, width=14).grid(row=2, column=1, padx=4, pady=(4, 0))
        ttk.Label(simulate, text="已等待(秒):").grid(row=2, column=2, sticky=tk.W, pady=(4, 0), padx=(8, 0))
        ttk.Entry(simulate, textvariable=self.qq_waited_sec_var, width=6).grid(row=2, column=3, padx=4, pady=(4, 0), sticky=tk.W)
        ttk.Label(simulate, text="消息内容:").grid(row=3, column=0, sticky=tk.W, pady=(6, 0))
        ttk.Entry(simulate, textvariable=self.qq_text_var, width=28).grid(row=3, column=1, columnspan=3, pady=(6, 0), sticky=tk.W)

        info = ttk.LabelFrame(body, text="运行信息", padding=8)
        info.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(info, textvariable=self.qq_status_text, foreground="#444").pack(anchor=tk.W)
        ttk.Label(info, textvariable=self.qq_webhook_url_var, foreground="#666").pack(anchor=tk.W, pady=(4, 0))

        # ── 左半部分：会话记录（占据左侧部分空间） ──
        chat_box = ttk.LabelFrame(self.root_frame, text="会话记录（消息与回复）", padding=8)
        chat_box.grid(row=0, column=0, sticky="nsew", padx=(2, 4))
        chat_box.grid_rowconfigure(0, weight=1)
        chat_box.grid_columnconfigure(0, weight=1)
        self.qq_chat_display = tk.Text(chat_box, wrap=tk.WORD, state=tk.DISABLED,
                                        font=("Microsoft YaHei UI", 9))
        self.qq_chat_display.grid(row=0, column=0, sticky="nsew")
        chat_scroll = ttk.Scrollbar(chat_box, orient=tk.VERTICAL, command=self.qq_chat_display.yview)
        chat_scroll.grid(row=0, column=1, sticky="ns")
        self.qq_chat_display.configure(yscrollcommand=chat_scroll.set)
        # 配置会话记录颜色标签
        self.qq_chat_display.tag_configure("msg_in", foreground="#1a73e8", font=("Microsoft YaHei UI", 9, "bold"))
        self.qq_chat_display.tag_configure("msg_out", foreground="#0d904f", font=("Microsoft YaHei UI", 9, "bold"))
        self.qq_chat_display.tag_configure("msg_sys", foreground="#888888", font=("Microsoft YaHei UI", 9))

    def _wire_state_persistence(self) -> None:
        tracked_vars = [
            self.text_api_provider_var,
            self.text_api_model_var,
            self.text_api_key_var,
            self.text_api_base_url_var,
            self.search_var,
            self.qq_group_var,
            self.qq_delay_var,
            self.qq_cooldown_var,
            self.qq_self_user_var,
            self.qq_group_edit_var,
            self.qq_group_new_var,
            self.qq_private_enabled_var,
            self.qq_enabled_var,
            self.qq_gateway_var,
            self.qq_connect_now_var,
            self.qq_prompt_var,
            self.qq_managed_api_base_var,
            self.qq_managed_token_var,
            self.qq_receive_token_var,
            self.qq_managed_account_var,
            self.qq_source_var,
            self.qq_chat_var,
            self.qq_sender_var,
            self.qq_waited_sec_var,
            self.qq_text_var,
        ]
        for variable in tracked_vars:
            variable.trace_add("write", lambda *_args: self._request_save())

    def _request_save(self) -> None:
        if self._loading_state or self._save_pending:
            return
        self._save_pending = True
        self.parent.after_idle(self._flush_save)

    def _flush_save(self) -> None:
        self._save_pending = False
        self._save_state()

    def append_qq_system_message(self, text: str) -> None:
        """在 QQ 会话记录区以灰色系统消息追加一行。"""
        try:
            from datetime import datetime as _dt
            ts = _dt.now().strftime("%H:%M:%S")
            self.qq_chat_display.configure(state=tk.NORMAL)
            self.qq_chat_display.insert(tk.END, f"[{ts}] ℹ️ 系统\n", "msg_sys")
            self.qq_chat_display.insert(tk.END, f"  {text}\n\n", "msg_sys")
            self.qq_chat_display.see(tk.END)
            self.qq_chat_display.configure(state=tk.DISABLED)
        except Exception:
            pass

    def _collect_state(self) -> dict[str, Any]:
        return {
            "text_api_provider": self.text_api_provider_var.get(),
            "text_api_model": self.text_api_model_var.get(),
            "text_api_key": self.text_api_key_var.get(),
            "text_api_base_url": self.text_api_base_url_var.get(),
            "enable_search": self.search_var.get(),
            "qq_group": self.qq_group_var.get(),
            "qq_delay": self.qq_delay_var.get(),
            "qq_cooldown": self.qq_cooldown_var.get(),
            "qq_self_user": self.qq_self_user_var.get(),
            "qq_group_edit": self.qq_group_edit_var.get(),
            "qq_group_new": self.qq_group_new_var.get(),
            "qq_private_enabled": self.qq_private_enabled_var.get(),
            "qq_enabled": self.qq_enabled_var.get(),
            "qq_gateway": self.qq_gateway_var.get(),
            "qq_connect_now": self.qq_connect_now_var.get(),
            "qq_prompt": self.qq_prompt_var.get(),
            "qq_managed_api_base": self.qq_managed_api_base_var.get(),
            "qq_managed_token": self.qq_managed_token_var.get(),
            "qq_receive_token": self.qq_receive_token_var.get(),
            "qq_managed_account": self.qq_managed_account_var.get(),
            "qq_image_recognition": self.qq_image_recognition_var.get(),
            "qq_source": self.qq_source_var.get(),
            "qq_chat": self.qq_chat_var.get(),
            "qq_sender": self.qq_sender_var.get(),
            "qq_waited_sec": self.qq_waited_sec_var.get(),
            "qq_text": self.qq_text_var.get(),
        }

    def _apply_state(self, data: dict[str, Any]) -> None:
        self._loading_state = True
        try:
            if "text_api_provider" in data:
                self.text_api_provider_var.set(str(data.get("text_api_provider", self.text_api_provider_var.get())))
            if "text_api_model" in data:
                self.text_api_model_var.set(str(data.get("text_api_model", self.text_api_model_var.get())))
            if "text_api_key" in data:
                self.text_api_key_var.set(str(data.get("text_api_key", self.text_api_key_var.get())))
            if "text_api_base_url" in data:
                self.text_api_base_url_var.set(str(data.get("text_api_base_url", self.text_api_base_url_var.get())))
            if "enable_search" in data:
                self.search_var.set(bool(data.get("enable_search", self.search_var.get())))
            if "qq_group" in data:
                self.qq_group_var.set(str(data.get("qq_group", self.qq_group_var.get())))
            if "qq_delay" in data:
                self.qq_delay_var.set(int(data.get("qq_delay", self.qq_delay_var.get())))
            if "qq_cooldown" in data:
                self.qq_cooldown_var.set(int(data.get("qq_cooldown", self.qq_cooldown_var.get())))
            if "qq_self_user" in data:
                self.qq_self_user_var.set(str(data.get("qq_self_user", self.qq_self_user_var.get())))
            if "qq_group_edit" in data:
                self.qq_group_edit_var.set(str(data.get("qq_group_edit", self.qq_group_edit_var.get())))
            if "qq_group_new" in data:
                self.qq_group_new_var.set(str(data.get("qq_group_new", self.qq_group_new_var.get())))
            if "qq_private_enabled" in data:
                self.qq_private_enabled_var.set(bool(data.get("qq_private_enabled", self.qq_private_enabled_var.get())))
            if "qq_enabled" in data:
                self.qq_enabled_var.set(bool(data.get("qq_enabled", self.qq_enabled_var.get())))
            if "qq_gateway" in data:
                self.qq_gateway_var.set(str(data.get("qq_gateway", self.qq_gateway_var.get())))
            if "qq_connect_now" in data:
                self.qq_connect_now_var.set(bool(data.get("qq_connect_now", self.qq_connect_now_var.get())))
            if "qq_prompt" in data:
                self.qq_prompt_var.set(str(data.get("qq_prompt", self.qq_prompt_var.get())))
            if "qq_managed_api_base" in data:
                self.qq_managed_api_base_var.set(str(data.get("qq_managed_api_base", self.qq_managed_api_base_var.get())))
            if "qq_managed_token" in data:
                self.qq_managed_token_var.set(str(data.get("qq_managed_token", self.qq_managed_token_var.get())))
            if "qq_receive_token" in data:
                self.qq_receive_token_var.set(str(data.get("qq_receive_token", self.qq_receive_token_var.get())))
            if "qq_managed_account" in data:
                self.qq_managed_account_var.set(str(data.get("qq_managed_account", self.qq_managed_account_var.get())))
            if "qq_source" in data:
                self.qq_source_var.set(str(data.get("qq_source", self.qq_source_var.get())))
            if "qq_chat" in data:
                self.qq_chat_var.set(str(data.get("qq_chat", self.qq_chat_var.get())))
            if "qq_sender" in data:
                self.qq_sender_var.set(str(data.get("qq_sender", self.qq_sender_var.get())))
            if "qq_waited_sec" in data:
                self.qq_waited_sec_var.set(int(data.get("qq_waited_sec", self.qq_waited_sec_var.get())))
            if "qq_image_recognition" in data:
                self.qq_image_recognition_var.set(bool(data.get("qq_image_recognition", self.qq_image_recognition_var.get())))
            if "qq_text" in data:
                self.qq_text_var.set(str(data.get("qq_text", self.qq_text_var.get())))
        finally:
            self._loading_state = False

    def _save_state(self) -> None:
        try:
            self.state_path.write_text(json.dumps(self._collect_state(), ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _load_state(self) -> None:
        if not self.state_path.exists():
            self._request_save()
            return
        try:
            raw = json.loads(self.state_path.read_text(encoding="utf-8"))
        except Exception:
            return
        if isinstance(raw, dict):
            self._apply_state(raw)
        self._request_save()

    def _refresh_from_tool_status(self) -> None:
        result = self.tool.run({"command": "get_status"})
        if not result.success:
            return
        meta = result.meta if isinstance(result.meta, dict) else {}
        if meta.get("reply_api_provider"):
            self.text_api_provider_var.set(str(meta.get("reply_api_provider", self.text_api_provider_var.get())))
        if meta.get("reply_api_model") is not None:
            self.text_api_model_var.set(str(meta.get("reply_api_model", self.text_api_model_var.get())))
        if meta.get("reply_api_key") is not None:
            self.text_api_key_var.set(str(meta.get("reply_api_key", self.text_api_key_var.get())))
        if meta.get("reply_api_base_url") is not None:
            self.text_api_base_url_var.set(str(meta.get("reply_api_base_url", self.text_api_base_url_var.get())))
        if meta.get("target_group_id") is not None:
            self.qq_group_var.set(str(meta.get("target_group_id", self.qq_group_var.get())))
        if meta.get("private_delay_sec") is not None:
            self.qq_delay_var.set(int(meta.get("private_delay_sec", self.qq_delay_var.get())))
        if meta.get("cooldown_sec") is not None:
            self.qq_cooldown_var.set(int(meta.get("cooldown_sec", self.qq_cooldown_var.get())))
        if meta.get("self_user_id") is not None:
            self.qq_self_user_var.set(str(meta.get("self_user_id", self.qq_self_user_var.get())))
        if meta.get("gateway_mode") is not None:
            self.qq_gateway_var.set(str(meta.get("gateway_mode", self.qq_gateway_var.get())))
        if meta.get("managed_account") is not None:
            self.qq_managed_account_var.set(str(meta.get("managed_account", self.qq_managed_account_var.get())))
        if meta.get("managed_api_base_url") is not None:
            self.qq_managed_api_base_var.set(str(meta.get("managed_api_base_url", self.qq_managed_api_base_var.get())))
        if meta.get("managed_access_token") is not None:
            self.qq_managed_token_var.set(str(meta.get("managed_access_token", self.qq_managed_token_var.get())))
        if meta.get("receive_token") is not None:
            self.qq_receive_token_var.set(str(meta.get("receive_token", self.qq_receive_token_var.get())))
        if meta.get("client_token") is not None:
            self.qq_receive_token_var.set(str(meta.get("client_token", self.qq_receive_token_var.get())))
        if meta.get("private_enabled") is not None:
            self.qq_private_enabled_var.set(bool(meta.get("private_enabled", self.qq_private_enabled_var.get())))
        if meta.get("enabled") is not None:
            self.qq_enabled_var.set(bool(meta.get("enabled", self.qq_enabled_var.get())))
        binding = meta.get("binding") if isinstance(meta.get("binding"), dict) else None
        binding_note = ""
        if isinstance(binding, dict) and binding.get("notes"):
            binding_note = str(binding.get("notes"))
        self.qq_status_text.set(
            f"状态已读取：enabled={bool(meta.get('enabled', True))} private={bool(meta.get('private_enabled', True))} "
            f"group={self.qq_group_var.get()} gateway={self.qq_gateway_var.get()}"
            + (f" | {binding_note}" if binding_note else "")
        )
        if meta.get("reply_api_base_url"):
            self.qq_webhook_url_var.set(f"NapCat API基址：{meta.get('reply_api_base_url')}")

    def _run_tool(self, command: str, payload: dict[str, Any]) -> None:
        result = self.tool.run({"command": command, **payload})
        if isinstance(result.meta, dict) and result.meta:
            self._apply_status_meta(result.meta)
        self.qq_status_text.set(str(result.output))
        self._request_save()

    def _apply_status_meta(self, meta: dict[str, Any]) -> None:
        if meta.get("reply_api_provider") is not None:
            self.text_api_provider_var.set(str(meta.get("reply_api_provider", self.text_api_provider_var.get())))
        if meta.get("reply_api_model") is not None:
            self.text_api_model_var.set(str(meta.get("reply_api_model", self.text_api_model_var.get())))
        if meta.get("reply_api_key") is not None:
            self.text_api_key_var.set(str(meta.get("reply_api_key", self.text_api_key_var.get())))
        if meta.get("reply_api_base_url") is not None:
            self.text_api_base_url_var.set(str(meta.get("reply_api_base_url", self.text_api_base_url_var.get())))
        if meta.get("target_group_id") is not None:
            self.qq_group_var.set(str(meta.get("target_group_id", self.qq_group_var.get())))
        if meta.get("private_delay_sec") is not None:
            self.qq_delay_var.set(int(meta.get("private_delay_sec", self.qq_delay_var.get())))
        if meta.get("cooldown_sec") is not None:
            self.qq_cooldown_var.set(int(meta.get("cooldown_sec", self.qq_cooldown_var.get())))
        if meta.get("self_user_id") is not None:
            self.qq_self_user_var.set(str(meta.get("self_user_id", self.qq_self_user_var.get())))
        if meta.get("gateway_mode") is not None:
            self.qq_gateway_var.set(str(meta.get("gateway_mode", self.qq_gateway_var.get())))
        if meta.get("managed_account") is not None:
            self.qq_managed_account_var.set(str(meta.get("managed_account", self.qq_managed_account_var.get())))
        if meta.get("managed_api_base_url") is not None:
            self.qq_managed_api_base_var.set(str(meta.get("managed_api_base_url", self.qq_managed_api_base_var.get())))
        if meta.get("managed_access_token") is not None:
            self.qq_managed_token_var.set(str(meta.get("managed_access_token", self.qq_managed_token_var.get())))
        if meta.get("private_enabled") is not None:
            self.qq_private_enabled_var.set(bool(meta.get("private_enabled", self.qq_private_enabled_var.get())))
        if meta.get("enabled") is not None:
            self.qq_enabled_var.set(bool(meta.get("enabled", self.qq_enabled_var.get())))
        if meta.get("receive_token") is not None:
            self.qq_receive_token_var.set(str(meta.get("receive_token", self.qq_receive_token_var.get())))
        if meta.get("client_token") is not None:
            self.qq_receive_token_var.set(str(meta.get("client_token", self.qq_receive_token_var.get())))
        if meta.get("event_post_url"):
            self.qq_webhook_url_var.set(f"NapCat事件接收地址：{meta.get('event_post_url')}")

    def on_qq_configure(self) -> None:
        group_ids = [item.strip() for item in self.qq_group_var.get().replace("，", ",").split(",") if item.strip()]
        result = self.tool.run(
            {
                "command": "configure",
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
                "receive_token": self.qq_receive_token_var.get().strip(),
                "reply_api_provider": self.text_api_provider_var.get().strip().lower() or "deepseek",
                "reply_api_model": self.text_api_model_var.get().strip(),
                "reply_api_key": self.text_api_key_var.get().strip(),
                "reply_api_base_url": self.text_api_base_url_var.get().strip(),
                "enable_image_recognition": bool(self.qq_image_recognition_var.get()),
            }
        )
        if result.success:
            self._apply_status_meta(result.meta if isinstance(result.meta, dict) else {})
        self.qq_status_text.set(result.output)
        self._request_save()

    def on_qq_bootstrap(self) -> None:
        result = self.tool.run(
            {
                "command": "bootstrap",
                "gateway_mode": self.qq_gateway_var.get().strip(),
                "connect_now": bool(self.qq_connect_now_var.get()),
                "managed_account": self.qq_managed_account_var.get().strip(),
                "managed_api_base_url": self.qq_managed_api_base_var.get().strip(),
                "managed_access_token": self.qq_managed_token_var.get().strip(),
                "receive_token": self.qq_receive_token_var.get().strip(),
                "search_roots": [str(self.workspace_dir)],
            }
        )
        if result.success:
            self._apply_status_meta(result.meta if isinstance(result.meta, dict) else {})
        self.qq_status_text.set(result.output)
        self._request_save()

    def on_qq_download_napcat(self) -> None:
        result = self.tool.run({"command": "download_napcat"})
        self.qq_status_text.set(result.output)
        self._request_save()

    def on_qq_group_add(self) -> None:
        group_id = self.qq_group_edit_var.get().strip()
        if not group_id:
            return
        result = self.tool.run({"command": "add_target_group", "group_id": group_id})
        self.qq_status_text.set(result.output)
        if result.success and isinstance(result.meta, dict):
            self._apply_status_meta(result.meta)
        self._request_save()

    def on_qq_group_remove(self) -> None:
        group_id = self.qq_group_edit_var.get().strip()
        if not group_id:
            return
        result = self.tool.run({"command": "remove_target_group", "group_id": group_id})
        self.qq_status_text.set(result.output)
        if result.success and isinstance(result.meta, dict):
            self._apply_status_meta(result.meta)
        self._request_save()

    def on_qq_group_update(self) -> None:
        old_group_id = self.qq_group_edit_var.get().strip()
        new_group_id = self.qq_group_new_var.get().strip()
        if not old_group_id or not new_group_id:
            return
        result = self.tool.run({"command": "update_target_group", "old_group_id": old_group_id, "new_group_id": new_group_id})
        self.qq_status_text.set(result.output)
        if result.success and isinstance(result.meta, dict):
            self._apply_status_meta(result.meta)
        self._request_save()

    def on_qq_bind_local_client_auto(self) -> None:
        result = self.tool.run(
            {
                "command": "bind_local_client_auto",
                "gateway_mode": self.qq_gateway_var.get().strip(),
                "search_roots": [str(self.workspace_dir)],
                "connect_now": bool(self.qq_connect_now_var.get()),
            }
        )
        self.qq_status_text.set(result.output)
        if result.success and isinstance(result.meta, dict):
            self._apply_status_meta(result.meta)
        self._request_save()

    def on_qq_status(self) -> None:
        self._restore_from_tool_status()
        self._request_save()

    def on_qq_pause(self) -> None:
        result = self.tool.run({"command": "pause"})
        self.qq_status_text.set(result.output)
        self._request_save()

    def on_qq_restart_webhook(self) -> None:
        """重启 QQ 事件 HTTP 服务器。"""
        self._stop_qq_webhook_server()
        self.root.update()
        import time as _time
        _time.sleep(0.3)
        self._start_qq_webhook_server()
        self.qq_panel.append_qq_system_message("事件服务器已重启。")

    def on_qq_resume(self) -> None:
        result = self.tool.run({"command": "resume"})
        self.qq_status_text.set(result.output)
        self._request_save()

    def on_qq_poll_pending(self) -> None:
        result = self.tool.run({"command": "poll_pending"})
        self.qq_status_text.set(result.output)
        self._request_save()

    def on_qq_simulate_message(self) -> None:
        payload = {
            "command": "handle_message",
            "source": self.qq_source_var.get().strip(),
            "chat_id": self.qq_chat_var.get().strip(),
            "sender_id": self.qq_sender_var.get().strip(),
            "text": self.qq_text_var.get().strip(),
        }
        if self.qq_source_var.get().strip() == "private":
            payload["waited_sec"] = int(self.qq_waited_sec_var.get())
        result = self.tool.run(payload)
        self.qq_status_text.set(result.output)
        if result.success and isinstance(result.meta, dict):
            self._apply_status_meta(result.meta)
        self._request_save()

    def on_qq_manual_replied(self) -> None:
        result = self.tool.run({"command": "user_replied", "chat_id": self.qq_chat_var.get().strip()})
        self.qq_status_text.set(result.output)
        self._request_save()

    def _restore_from_tool_status(self) -> None:
        result = self.tool.run({"command": "get_status"})
        if not result.success:
            return
        self._apply_status_meta(result.meta if isinstance(result.meta, dict) else {})
        status = result.meta if isinstance(result.meta, dict) else {}
        if status.get("binding") and isinstance(status.get("binding"), dict):
            notes = str(status["binding"].get("notes", "")).strip()
            if notes:
                self.qq_webhook_url_var.set(notes)
        self.qq_status_text.set(str(result.output))



class RecycleBinPanel:
    """回收站可视化面板：显示回收站内容，提供清空、单个文件彻底删除、单个文件还原功能。"""

    # 元数据文件名：存储原始路径
    _META_FILE = ".recycle_meta.json"

    def __init__(self, parent: ttk.Frame, workspace_dir: Path) -> None:
        self.parent = parent
        self.workspace_dir = workspace_dir
        self._recycle_bin_dir = workspace_dir / ".recycle_bin"

        # 元数据：{ 回收站文件名: 原始绝对路径 }
        self._meta: dict[str, str] = {}
        self._load_meta()

        # UI
        self.root_frame = ttk.Frame(parent, padding=12)
        self.root_frame.grid(row=0, column=0, sticky="nsew")
        self.root_frame.grid_rowconfigure(0, weight=1)
        self.root_frame.grid_columnconfigure(0, weight=1)

        self._build_ui()
        self._refresh()

    # ── 元数据管理 ────────────────────────────────────────────────────

    def _load_meta(self) -> None:
        meta_path = self._recycle_bin_dir / self._META_FILE
        if meta_path.exists():
            try:
                data = json.loads(meta_path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    self._meta = {str(k): str(v) for k, v in data.items()}
                    return
            except Exception:
                pass
        self._meta = {}

    def _save_meta(self) -> None:
        if not self._recycle_bin_dir.exists():
            self._recycle_bin_dir.mkdir(parents=True, exist_ok=True)
        meta_path = self._recycle_bin_dir / self._META_FILE
        try:
            meta_path.write_text(json.dumps(self._meta, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _set_meta_source(self, recycle_name: str, source_path: str) -> None:
        self._meta[recycle_name] = source_path
        self._save_meta()

    def _remove_meta(self, recycle_name: str) -> None:
        self._meta.pop(recycle_name, None)
        self._save_meta()

    def _get_meta_source(self, recycle_name: str) -> str | None:
        return self._meta.get(recycle_name)

    # ── UI ────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        header = ttk.Frame(self.root_frame)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        header.grid_columnconfigure(0, weight=1)
        ttk.Label(header, text="回收站", font=("Microsoft YaHei UI", 12, "bold")).grid(row=0, column=0, sticky=tk.W)

        self._status_var = tk.StringVar(value="")
        ttk.Label(header, textvariable=self._status_var, foreground="#666").grid(row=1, column=0, sticky=tk.W, pady=(4, 0))

        # 操作按钮行
        action_frame = ttk.Frame(self.root_frame)
        action_frame.grid(row=1, column=0, sticky="ew", pady=(0, 6))
        self.restore_btn = ttk.Button(action_frame, text="还原选中", command=self._on_restore_selected)
        self.restore_btn.pack(side=tk.LEFT, padx=(0, 6))
        self.delete_btn = ttk.Button(action_frame, text="彻底删除选中", command=self._on_permanent_delete_selected)
        self.delete_btn.pack(side=tk.LEFT, padx=(0, 12))
        self.empty_btn = ttk.Button(action_frame, text="清空回收站", command=self._on_empty)
        self.empty_btn.pack(side=tk.LEFT, padx=(0, 6))
        self.refresh_btn = ttk.Button(action_frame, text="刷新", command=self._refresh)
        self.refresh_btn.pack(side=tk.LEFT)
        # 初态禁用
        self.restore_btn.configure(state=tk.DISABLED)
        self.delete_btn.configure(state=tk.DISABLED)

        # 内容区：Treeview
        columns = ("name", "source", "size", "date")
        self.tree = ttk.Treeview(self.root_frame, columns=columns, show="headings", height=12)
        self.tree.heading("name", text="文件名")
        self.tree.heading("source", text="来源路径")
        self.tree.heading("size", text="大小")
        self.tree.heading("date", text="删除时间")
        self.tree.column("name", width=200, minwidth=120)
        self.tree.column("source", width=350, minwidth=200)
        self.tree.column("size", width=100, minwidth=80, anchor=tk.E)
        self.tree.column("date", width=160, minwidth=120)
        self.tree.grid(row=2, column=0, sticky="nsew")
        self.root_frame.grid_rowconfigure(2, weight=1)

        scrollbar = ttk.Scrollbar(self.root_frame, orient=tk.VERTICAL, command=self.tree.yview)
        scrollbar.grid(row=2, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scrollbar.set)

        # 选中事件：启用/禁用按钮
        self.tree.bind("<<TreeviewSelect>>", self._on_selection_changed)

        # 右键菜单
        self._context_menu = tk.Menu(self.tree, tearoff=0)
        self._context_menu.add_command(label="还原到源路径", command=self._on_restore_selected)
        self._context_menu.add_command(label="彻底删除", command=self._on_permanent_delete_selected)
        self.tree.bind("<Button-3>", self._on_context_menu)

        # 说明文字
        info_text = (
            "本地：工具在非 Windows 系统下删除时，文件移至 .recycle_bin 目录。选中后可用「还原」或「彻底删除」。\n"
            "系统：Windows 回收站 — 通过 SHFileOperation 删除的文件自动进入，仅支持「清空回收站」。\n\n"
            "提示：还原操作将文件移回原始路径；彻底删除会永久销毁文件，无法恢复！"
        )
        ttk.Label(self.root_frame, text=info_text, foreground="#888", wraplength=800, justify=tk.LEFT).grid(
            row=3, column=0, columnspan=2, sticky=tk.W, pady=(8, 0)
        )

    def _on_selection_changed(self, _event: Any = None) -> None:
        """根据选中项启用/禁用操作按钮。"""
        selected = self.tree.selection()
        # 检查是否有真实文件行（非系统回收站摘要行）
        has_real_file = False
        has_windows_summary = False
        for item_id in selected:
            values = self.tree.item(item_id, "values")
            if values and values[1] == "系统回收站":
                has_windows_summary = True
            else:
                has_real_file = True

        if has_real_file:
            self.restore_btn.configure(state=tk.NORMAL)
            self.delete_btn.configure(state=tk.NORMAL)
        else:
            self.restore_btn.configure(state=tk.DISABLED)
            self.delete_btn.configure(state=tk.DISABLED)

    def _on_context_menu(self, event: Any) -> None:
        """右键菜单。"""
        item_id = self.tree.identify_row(event.y)
        if not item_id:
            return
        self.tree.selection_set(item_id)
        values = self.tree.item(item_id, "values")
        if values and values[1] == "系统回收站":
            return  # 系统回收站行无单文件操作
        self._context_menu.tk_popup(event.x_root, event.y_root)

    def _refresh(self) -> None:
        """刷新回收站列表。"""
        # 重新加载元数据
        self._load_meta()

        for item in self.tree.get_children():
            self.tree.delete(item)

        local_count = 0
        # 1) 本地 .recycle_bin 目录（排除元数据文件本身）
        if self._recycle_bin_dir.exists():
            for f in sorted(self._recycle_bin_dir.iterdir()):
                if f.is_file() and f.name != self._META_FILE:
                    size_str = self._format_size(f.stat().st_size)
                    mtime = datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                    # 从元数据读取原始路径
                    source = self._get_meta_source(f.name) or str(f.relative_to(self._recycle_bin_dir.parent))
                    # 如果源路径不存在，标记为（已移动）
                    if not Path(source).exists():
                        source_display = source
                    else:
                        source_display = source
                    self.tree.insert("", tk.END, values=(
                        f.name,
                        source_display,
                        size_str,
                        mtime,
                    ))
                    local_count += 1

        # 2) 通过 ctypes 查询 Windows 回收站统计信息
        win_count = self._count_windows_recycle_bin()
        total_items = local_count + (1 if win_count > 0 else 0)  # 系统回收站算一行
        win_summary_text = ""
        if win_count > 0:
            win_summary_text = f"(Windows 回收站 - 约 {win_count} 个文件)"
            self.tree.insert("", tk.END, values=(
                win_summary_text,
                "系统回收站",
                "",
                "",
            ))

        # 状态文字
        parts = []
        if local_count > 0:
            parts.append(f"本地 {local_count} 项")
        if win_count > 0:
            parts.append(f"系统约 {win_count} 项")
        self._status_var.set(f"共 {', '.join(parts)}" if parts else "回收站是空的")

        # 按钮状态
        has_items = len(self.tree.get_children()) > 0
        self.empty_btn.configure(state=tk.NORMAL if has_items else tk.DISABLED)
        # 选中状态已由 _on_selection_changed 处理
        self.restore_btn.configure(state=tk.DISABLED)
        self.delete_btn.configure(state=tk.DISABLED)

    # ── 单文件操作 ────────────────────────────────────────────────────

    def _get_selected_local_file(self) -> tuple[str, str] | None:
        """获取选中的本地回收站文件名和原始路径。选中系统回收站行则返回 None。"""
        selected = self.tree.selection()
        if not selected:
            return None
        values = self.tree.item(selected[0], "values")
        if not values or values[1] == "系统回收站":
            return None
        recycle_name = str(values[0])
        source_path = self._get_meta_source(recycle_name)
        return recycle_name, source_path or ""

    def _on_restore_selected(self) -> None:
        """还原选中的文件到原始路径。"""
        info = self._get_selected_local_file()
        if info is None:
            messagebox.showwarning("还原", "请先选中一个本地回收站中的文件。", parent=self.parent)
            return
        recycle_name, source_path = info
        recycle_file = self._recycle_bin_dir / recycle_name

        if not recycle_file.exists():
            messagebox.showerror("还原", f"回收站中找不到文件：{recycle_name}", parent=self.parent)
            self._remove_meta(recycle_name)
            self._refresh()
            return

        # 确定目标路径
        if source_path and Path(source_path).exists():
            # 源路径仍存在 → 询问是否覆盖
            if not messagebox.askyesno(
                "还原确认",
                f"原始路径已存在文件：\n{source_path}\n\n是否覆盖？",
                parent=self.parent,
            ):
                return
            target = Path(source_path)
        elif source_path:
            # 源路径不存在但记录中有 → 直接还原
            target = Path(source_path)
            target.parent.mkdir(parents=True, exist_ok=True)
        else:
            # 没有源路径记录 → 还原到 workspace 根目录
            target = self.workspace_dir / recycle_name

        try:
            shutil.move(str(recycle_file), str(target))
            self._remove_meta(recycle_name)
            self._refresh()
            messagebox.showinfo("还原", f"已还原到：{target}", parent=self.parent)
        except Exception as exc:
            messagebox.showerror("还原失败", f"还原文件时出错：{exc}", parent=self.parent)

    def _on_permanent_delete_selected(self) -> None:
        """彻底删除选中的文件。"""
        info = self._get_selected_local_file()
        if info is None:
            messagebox.showwarning("彻底删除", "请先选中一个本地回收站中的文件。", parent=self.parent)
            return
        recycle_name, source_path = info
        recycle_file = self._recycle_bin_dir / recycle_name

        if not recycle_file.exists():
            messagebox.showerror("彻底删除", f"回收站中找不到文件：{recycle_name}", parent=self.parent)
            self._remove_meta(recycle_name)
            self._refresh()
            return

        if not messagebox.askyesno(
            "彻底删除",
            f"确认永久删除「{recycle_name}」？\n\n该操作不可撤销！",
            parent=self.parent,
        ):
            return

        try:
            recycle_file.unlink()
            self._remove_meta(recycle_name)
            self._refresh()
            messagebox.showinfo("彻底删除", f"已永久删除：{recycle_name}", parent=self.parent)
        except Exception as exc:
            messagebox.showerror("删除失败", f"删除文件时出错：{exc}", parent=self.parent)

    # ── 清空操作（保留已有功能） ────────────────────────────────────────

    def _count_windows_recycle_bin(self) -> int:
        """估算 Windows 回收站中的文件数量。"""
        try:
            import ctypes.wintypes
            shell32 = ctypes.windll.shell32
            shell32.SHQueryRecycleBinW.restype = ctypes.c_long
            shell32.SHQueryRecycleBinW.argtypes = [ctypes.c_wchar_p, ctypes.c_void_p]

            class SHQUERYRBINFO(ctypes.Structure):
                _fields_ = [
                    ("cbSize", ctypes.wintypes.DWORD),
                    ("i64Size", ctypes.c_int64),
                    ("i64NumItems", ctypes.c_int64),
                ]

            info = SHQUERYRBINFO()
            info.cbSize = ctypes.sizeof(SHQUERYRBINFO)
            result = shell32.SHQueryRecycleBinW(None, ctypes.byref(info))
            if result == 0:
                return int(info.i64NumItems)
        except Exception:
            pass
        return 0

    def _on_empty(self) -> None:
        """清空回收站。"""
        local_count = sum(1 for f in self.tree.get_children() if self.tree.item(f, "values")[1] != "系统回收站")
        win_count = self._count_windows_recycle_bin()

        total_desc = []
        if local_count > 0:
            total_desc.append(f"本地 {local_count} 项")
        if win_count > 0:
            total_desc.append(f"系统约 {win_count} 项")

        if not total_desc:
            return

        if not messagebox.askyesno(
            "清空回收站",
            f"回收站中有 {'、'.join(total_desc)}，确认永久删除？\n\n该操作不可撤销！",
            parent=self.parent,
        ):
            return

        success = True
        messages = []

        # 清空本地 .recycle_bin
        if self._recycle_bin_dir.exists():
            try:
                for f in list(self._recycle_bin_dir.iterdir()):
                    try:
                        if f.is_file():
                            f.unlink()
                        elif f.is_dir():
                            shutil.rmtree(str(f))
                    except Exception as exc:
                        messages.append(f"删除 {f.name} 失败：{exc}")
                        success = False
                # 清空元数据
                self._meta.clear()
                self._save_meta()
                # 如果空目录也删除
                if self._recycle_bin_dir.exists() and not any(self._recycle_bin_dir.iterdir()):
                    self._recycle_bin_dir.rmdir()
            except Exception as exc:
                messages.append(f"清空本地回收站失败：{exc}")
                success = False

        # 清空 Windows 系统回收站
        if win_count > 0:
            try:
                SHEmptyRecycleBinW = ctypes.windll.shell32.SHEmptyRecycleBinW
                SHEmptyRecycleBinW.restype = ctypes.c_long
                SHEmptyRecycleBinW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint]
                SHERB_NOCONFIRMATION = 0x00000001
                SHERB_NOPROGRESSUI = 0x00000002
                SHERB_NOSOUND = 0x00000004
                result = SHEmptyRecycleBinW(None, None, SHERB_NOCONFIRMATION | SHERB_NOPROGRESSUI | SHERB_NOSOUND)
                if result == 0:
                    messages.append("Windows 系统回收站已清空。")
                else:
                    messages.append(f"清空系统回收站失败，错误码={result}")
                    success = False
            except Exception as exc:
                messages.append(f"清空系统回收站异常：{exc}")
                success = False

        self._refresh()
        msg = "；".join(messages) or ("已清空回收站。" if success else "清空回收站时遇到问题。")
        self._status_var.set(msg)
        messagebox.showinfo("回收站", msg, parent=self.parent)

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        if size_bytes < 1024:
            return f"{size_bytes} B"
        if size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        return f"{size_bytes / (1024 * 1024):.1f} MB"


# ── QQ 事件接收 Webhook ──────────────────────────────────────────────


import http.server as _http_server


class _QQWebhookRequestHandler(_http_server.BaseHTTPRequestHandler):
    """接收 NapCat / OneBot 事件的本地 HTTP 入口。"""

    server_version = "ClawminiQQWebhook/1.0"
    # 可通过 server.app.qq_panel.qq_receive_token_var.get() 获取当前接收 token

    def _check_auth(self) -> bool:
        """验证接收 token（如果已配置）。
        NapCat httpClients 推送事件时通常不携带 Authorization 头，
        所以如果请求方未提供 token，我们仍然放行（仅记录）。
        """
        auth_header = self.headers.get("Authorization", "")
        bearer_token = auth_header
        if bearer_token.lower().startswith("bearer "):
            bearer_token = bearer_token[7:].strip()
        if not bearer_token:
            bearer_token = self.headers.get("X-Access-Token", "")
        if not bearer_token:
            # NapCat httpClients 推送时不带 token，放行
            return True
        server = cast(_QQWebhookServer, self.server)
        try:
            expected = server.app.qq_panel.qq_receive_token_var.get().strip()
        except Exception:
            expected = ""
        if not expected:
            return True  # 未配置 token 时不验证
        return bearer_token == expected

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

        # 验证接收 token
        if not self._check_auth():
            server = cast(_QQWebhookServer, self.server)
            auth_h = self.headers.get("Authorization", "(none)")
            try:
                expected = server.app.qq_panel.qq_receive_token_var.get().strip()
            except Exception:
                expected = ""
            print(f"[QQWebhook] 401 auth failed: expected='{expected}' auth='{auth_h}'")
            self.send_response(401)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            response = json.dumps({"ok": False, "error": "Unauthorized"}, ensure_ascii=False).encode("utf-8")
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)
            return

        raw_body = self._read_request_body()
        try:
            payload = json.loads(raw_body.decode("utf-8")) if raw_body else {}
        except Exception:
            print(f"[QQWebhook] 400 invalid JSON: {raw_body.decode('utf-8', errors='ignore')[:200]}")
            self.send_error(400, "Invalid JSON")
            return
        if not isinstance(payload, dict):
            payload = {"value": payload}

        post_type = payload.get("post_type", "unknown")
        msg_type = payload.get("message_type", "")
        print(f"[QQWebhook] 200 event: post_type={post_type} message_type={msg_type} path={self.path}")

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
        # OneBot 快速操作响应：返回空 JSON 即可，NapCat 不强制要求 quick operation
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


class _QQWebhookServer(_http_server.ThreadingHTTPServer):
    """绑定到 workspace app 的本地 webhook 服务器。"""

    app: "WorkspaceFileApp"

    def __init__(self, server_address: tuple[str, int], RequestHandlerClass: type[_http_server.BaseHTTPRequestHandler], app: "WorkspaceFileApp") -> None:
        super().__init__(server_address, RequestHandlerClass)
        self.app = app

    def __repr__(self) -> str:
        return f"_QQWebhookServer(addr={self.server_address})"


class WorkspaceFileApp:
    def __init__(self, root: tk.Tk, workspace_dir: Path) -> None:
        self.root = root
        self.workspace_dir = workspace_dir
        self.manager = WorkspaceSessionManager(workspace_dir)

        self.root.title("Clawmini 工作区会话器")
        self.root.geometry("1180x760")
        self.root.minsize(980, 620)
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

        self.session_list: tk.Listbox
        self.transcript: ScrolledText
        self.session_input: ScrolledText
        self.console_input: ScrolledText
        self.console_box: ttk.LabelFrame
        self.console_visible = False
        self._ai_busy = False
        self.status_var = tk.StringVar(value="")
        self.help_var = tk.StringVar(
            value="自然语言直接描述需求：文件/图片/文稿/会话管理/设置修改，AI 自动处理。"
        )
        self.home_notebook: ttk.Notebook

        self.qq_webhook_server: _QQWebhookServer | None = None
        self.qq_webhook_server_thread: threading.Thread | None = None
        self.response_queue: queue.Queue[tuple[str, dict[str, Any]]] = queue.Queue()

        self._build_ui()
        self._refresh_session_list()
        self._show_active_session()
        self._start_qq_webhook_server()
        self._poll_queue()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.bind_all("<Control-Return>", self._handle_control_enter)

    def _build_ui(self) -> None:
        self.home_notebook = ttk.Notebook(self.root)
        self.home_notebook.grid(row=0, column=0, sticky="nsew")

        file_page = ttk.Frame(self.home_notebook)
        file_page.grid_rowconfigure(1, weight=1)
        file_page.grid_rowconfigure(2, weight=0)
        file_page.grid_columnconfigure(0, weight=1)

        qq_page = ttk.Frame(self.home_notebook, padding=18)
        qq_page.grid_rowconfigure(0, weight=1)
        qq_page.grid_columnconfigure(0, weight=1)

        recycle_page = ttk.Frame(self.home_notebook)
        recycle_page.grid_rowconfigure(0, weight=1)
        recycle_page.grid_columnconfigure(0, weight=1)

        self.home_notebook.add(file_page, text="文件管理")
        self.home_notebook.add(qq_page, text="QQ自动回复")
        self.home_notebook.add(recycle_page, text="回收站")

        top = ttk.Frame(file_page, padding=(10, 10, 10, 6))
        top.grid(row=0, column=0, sticky="ew")
        top.grid_columnconfigure(0, weight=1)
        title_row = ttk.Frame(top)
        title_row.grid(row=0, column=0, sticky="w")
        ttk.Label(title_row, text="Clawmini 工作区会话器", font=("Microsoft YaHei UI", 15, "bold")).pack(side=tk.LEFT)
        # 设置按钮（打开可视化设置窗口）
        right_tools = ttk.Frame(top)
        right_tools.grid(row=0, column=1, sticky="e")
        ttk.Button(right_tools, text="帮助", width=5, command=self._show_help).pack(side=tk.RIGHT, padx=(0, 4))
        ttk.Button(right_tools, text="控制台", command=self._toggle_console_panel).pack(side=tk.RIGHT, padx=(6, 0))
        ttk.Button(right_tools, text="⚙", width=3, command=self._open_settings_window).pack(side=tk.RIGHT)
        ttk.Label(top, textvariable=self.help_var, foreground="#666").grid(row=1, column=0, sticky="w", pady=(4, 0))

        main = ttk.PanedWindow(file_page, orient=tk.HORIZONTAL)
        main.grid(row=1, column=0, sticky="nsew")

        session_panel = ttk.Frame(main, padding=10)
        session_panel.grid_rowconfigure(0, weight=1)
        session_panel.grid_rowconfigure(1, weight=0)
        session_panel.grid_columnconfigure(0, weight=1)
        main.add(session_panel, weight=1)

        transcript_panel = ttk.Frame(main, padding=(0, 10, 10, 10))
        transcript_panel.grid_rowconfigure(0, weight=1)
        transcript_panel.grid_columnconfigure(0, weight=1)
        main.add(transcript_panel, weight=3)

        session_box = ttk.LabelFrame(session_panel, text="会话区", padding=8)
        session_box.grid(row=0, column=0, sticky="nsew")
        session_box.grid_rowconfigure(1, weight=1)
        session_box.grid_columnconfigure(0, weight=1)

        button_row = ttk.Frame(session_box)
        button_row.grid(row=0, column=0, sticky="ew")
        ttk.Button(button_row, text="新建", command=self._new_session).pack(side=tk.LEFT)
        ttk.Button(button_row, text="删除", command=self._delete_session).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(button_row, text="重命名", command=self._rename_session).pack(side=tk.LEFT, padx=(6, 0))

        self.session_list = tk.Listbox(session_box, activestyle="dotbox")
        self.session_list.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        self.session_list.bind("<<ListboxSelect>>", self._on_session_selected)
        self.session_list.bind("<Double-Button-1>", self._on_session_open)

        self.status_label = ttk.Label(session_box, textvariable=self.status_var, foreground="#555", wraplength=280, justify=tk.LEFT)
        self.status_label.grid(row=2, column=0, sticky="w", pady=(8, 0))

        session_input_box = ttk.LabelFrame(session_panel, text="会话输入", padding=8)
        session_input_box.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        session_input_box.grid_columnconfigure(0, weight=1)

        self.session_input = ScrolledText(session_input_box, height=5, wrap=tk.WORD, font=("Microsoft YaHei UI", 10))
        self.session_input.grid(row=0, column=0, sticky="ew")
        self.session_input.bind("<Control-Return>", self._handle_control_enter)

        session_input_actions = ttk.Frame(session_input_box)
        session_input_actions.grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Button(session_input_actions, text="发送", command=self._send_session_input).pack(side=tk.LEFT)
        ttk.Button(session_input_actions, text="清空", command=self._clear_session_input).pack(side=tk.LEFT, padx=(6, 0))

        transcript_box = ttk.LabelFrame(transcript_panel, text="当前会话内容", padding=8)
        transcript_box.grid(row=0, column=0, sticky="nsew")
        transcript_box.grid_rowconfigure(0, weight=1)
        transcript_box.grid_columnconfigure(0, weight=1)
        self.transcript = ScrolledText(transcript_box, wrap=tk.WORD, font=("Microsoft YaHei UI", 10))
        self.transcript.grid(row=0, column=0, sticky="nsew")
        self.transcript.configure(state="disabled")

        self.console_box = ttk.LabelFrame(file_page, text="底部控制台", padding=8)
        self.console_box.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 10))
        self.console_box.grid_remove()
        self.console_box.grid_columnconfigure(0, weight=1)

        self.console_input = ScrolledText(self.console_box, height=5, wrap=tk.WORD, font=("Microsoft YaHei UI", 10))
        self.console_input.grid(row=0, column=0, columnspan=3, sticky="ew")

        ttk.Button(self.console_box, text="发送", command=self._send_console_input).grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Button(self.console_box, text="清空输入", command=self._clear_console_input).grid(row=1, column=1, sticky="w", padx=(8, 0), pady=(8, 0))
        ttk.Button(self.console_box, text="帮助", command=self._show_help).grid(row=1, column=2, sticky="w", padx=(8, 0), pady=(8, 0))

        self.qq_panel = QQAutoReplyPanel(qq_page, self.workspace_dir)
        self.recycle_panel = RecycleBinPanel(recycle_page, self.workspace_dir)

    @staticmethod
    def _render_markdown_as_text(md: str) -> str:
        """将 Markdown 源码转为可读的纯文本（去除标记符号）。"""
        import re
        lines = md.split("\n")
        out: list[str] = []
        for line in lines:
            # 跳过分隔线
            if re.match(r"^-{3,}$", line.strip()):
                out.append("")
                continue
            # 去掉代码块标记
            if line.strip().startswith("```"):
                out.append("")
                continue
            # 去掉标题 #
            stripped = line.lstrip()
            if stripped.startswith("#"):
                level = len(stripped.split(" ")[0])
                text = stripped.lstrip("# ").strip()
                prefix = "" if level == 1 else "  " * (level - 1)
                out.append(f"{prefix}{text}")
                out.append("")
                continue
            # 去掉表格的 | 和 --- 分隔行
            if re.match(r"^\|[\s-]+", line):
                if re.search(r"-{2,}", line):
                    continue
                cells = [c.strip() for c in line.strip(" |").split("|")]
                out.append("  " + "  |  ".join(cells))
                continue
            # 去掉行内加粗、斜体、行内代码
            line = re.sub(r"\*\*(.+?)\*\*", r"\1", line)
            line = re.sub(r"\*(.+?)\*", r"\1", line)
            line = re.sub(r"`(.+?)`", r"\1", line)
            # 去掉 blockquote >
            line = re.sub(r"^>\s?", "", line)
            out.append(line)
        return "\n".join(out)

    def _show_help(self) -> None:
        """打开帮助文档。"""
        help_path = self.workspace_dir.parent / "help.md"
        try:
            content = help_path.read_text(encoding="utf-8")
        except Exception:
            messagebox.showerror("错误", "找不到帮助文件 help.md")
            return
        content = self._render_markdown_as_text(content)
        win = tk.Toplevel(self.root)
        win.title("Clawmini 帮助")
        win.geometry("640x520")
        text = tk.Text(win, wrap=tk.WORD, font=("Microsoft YaHei UI", 10))
        text.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        text.insert("1.0", content)
        text.configure(state=tk.DISABLED)
        scrollbar = ttk.Scrollbar(win, orient=tk.VERTICAL, command=text.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        text.configure(yscrollcommand=scrollbar.set)

    def _toggle_console_panel(self) -> None:
        if self.console_visible:
            self.console_box.grid_remove()
            self.console_visible = False
        else:
            self.console_box.grid()
            self.console_visible = True

    def _handle_control_enter(self, _event: tk.Event | None = None) -> str:
        focused = self.root.focus_get()
        if focused == self.session_input:
            self._send_session_input()
            return "break"
        if focused == self.console_input or self.console_visible:
            self._send_console_input()
            return "break"
        self._send_session_input()
        return "break"

    def _open_settings_window(self) -> None:
        """打开或激活可视化设置窗口。"""
        if hasattr(self, "settings_window") and self.settings_window.winfo_exists():
            try:
                self.settings_window.deiconify()
                self.settings_window.lift()
            except Exception:
                pass
            return

        provider_cfgs = self.manager.settings.setdefault("provider_configs", self.manager._default_settings()["provider_configs"])
        current_provider = str(self.manager.settings.get("model_provider", "mock")).strip().lower() or "mock"

        # 从 provider_configs 加载当前 provider 的独立配置
        def _load_provider_config(prov: str) -> dict[str, str]:
            pcfg = provider_cfgs.get(prov, {})
            return {
                "model_name": pcfg.get("model_name", ""),
                "api_key": pcfg.get("api_key", ""),
                "base_url": pcfg.get("base_url", ""),
            }

        self.model_provider_var = tk.StringVar(value=current_provider)
        pcfg_init = _load_provider_config(current_provider)
        self.model_name_var = tk.StringVar(value=pcfg_init["model_name"] or self.manager.settings.get("model_name", ""))
        self.api_key_var = tk.StringVar(value=pcfg_init["api_key"] or self.manager.settings.get("api_key", ""))
        self.base_url_var = tk.StringVar(value=pcfg_init["base_url"] or self.manager.settings.get("base_url", ""))
        try:
            port_value = int(self.manager.settings.get("port", 17888))
        except Exception:
            port_value = 17888
        self.port_var = tk.IntVar(value=port_value)
        self.enable_search_var = tk.BooleanVar(value=self.manager.settings.get("enable_search", False))

        self.settings_window = tk.Toplevel(self.root)
        self.settings_window.title("设置")
        self.settings_window.transient(self.root)
        frm = ttk.Frame(self.settings_window, padding=12)
        frm.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frm, text="Provider:").grid(row=0, column=0, sticky=tk.W, pady=(0, 6))
        provider_combo = ttk.Combobox(frm, textvariable=self.model_provider_var, values=["openai", "deepseek", "qwen", "mock"], width=24, state="readonly")
        provider_combo.grid(row=0, column=1, sticky=tk.W, padx=6, pady=(0, 6))
        # 切换 provider 时切换到对应的独立缓存配置
        def _on_provider_change(*_args: object) -> None:
            prov = self.model_provider_var.get()
            pcfg = _load_provider_config(prov)
            self.model_name_var.set(pcfg["model_name"])
            self.api_key_var.set(pcfg["api_key"])
            self.base_url_var.set(pcfg["base_url"])
        self.model_provider_var.trace_add("write", _on_provider_change)

        ttk.Label(frm, text="Model:").grid(row=1, column=0, sticky=tk.W)
        ttk.Entry(frm, textvariable=self.model_name_var, width=36).grid(row=1, column=1, sticky=tk.W, padx=6, pady=(0, 6))

        ttk.Label(frm, text="API Key:").grid(row=2, column=0, sticky=tk.W)
        ttk.Entry(frm, textvariable=self.api_key_var, width=36).grid(row=2, column=1, sticky=tk.W, padx=6, pady=(0, 6))

        ttk.Label(frm, text="Base URL:").grid(row=3, column=0, sticky=tk.W)
        ttk.Entry(frm, textvariable=self.base_url_var, width=36).grid(row=3, column=1, sticky=tk.W, padx=6, pady=(0, 6))

        ttk.Label(frm, text="Port:").grid(row=4, column=0, sticky=tk.W)
        ttk.Entry(frm, textvariable=self.port_var, width=12).grid(row=4, column=1, sticky=tk.W, padx=6, pady=(0, 6))

        ttk.Checkbutton(frm, text="联网搜索 🔍（DeepSeek/Qwen 可用）", variable=self.enable_search_var).grid(row=5, column=0, columnspan=2, sticky=tk.W, pady=(0, 6))

        btn_row = ttk.Frame(frm)
        btn_row.grid(row=6, column=0, columnspan=2, pady=(10, 0))
        ttk.Button(btn_row, text="保存", command=self._save_workspace_settings).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btn_row, text="取消", command=lambda: self.settings_window.destroy()).pack(side=tk.LEFT)

        # Ensure window is centered relative to root
        self.settings_window.grab_set()

    def _save_workspace_settings(self) -> None:
        # Validate and persist settings via manager
        try:
            port = int(self.port_var.get())
        except Exception:
            messagebox.showerror("设置错误", f"端口必须为整数：{self.port_var.get()}", parent=self.settings_window)
            return

        provider = str(self.model_provider_var.get()).strip().lower()
        # 将当前 provider 的独立配置写入 provider_configs
        provider_cfgs = self.manager.settings.setdefault("provider_configs", {})
        provider_cfgs[provider] = {
            "model_name": str(self.model_name_var.get()).strip(),
            "api_key": str(self.api_key_var.get()).strip(),
            "base_url": str(self.base_url_var.get()).strip(),
        }
        updates = {
            "model_provider": provider,
            "model_name": str(self.model_name_var.get()).strip(),
            "api_key": str(self.api_key_var.get()).strip(),
            "base_url": str(self.base_url_var.get()).strip(),
            "port": port,
            "enable_search": self.enable_search_var.get(),
            "provider_configs": provider_cfgs,
        }
        self.manager.update_settings(updates)
        # 显示保存反馈
        self._append_transcript_line("系统", f"设置已保存：{json.dumps(self.manager.settings, ensure_ascii=False)}")
        try:
            self.settings_window.destroy()
        except Exception:
            pass
        # 让 UI 刷新显示最新设置
        self._show_active_session()

    def _clear_console_input(self) -> None:
        self.console_input.delete("1.0", tk.END)

    def _clear_session_input(self) -> None:
        self.session_input.delete("1.0", tk.END)

    def _send_session_input(self) -> None:
        raw_text = self.session_input.get("1.0", tk.END).strip()
        if not raw_text:
            return
        self._clear_session_input()
        self._submit_workspace_text(raw_text)

    def _submit_workspace_text(self, raw_text: str) -> None:
        if self._handle_command(raw_text):
            return

        if self._handle_recycle_command(raw_text):
            return

        session = self.manager.active_session()

        self._append_transcript_line("用户", raw_text)

        # 检查是否已有后台任务在运行
        if hasattr(self, "_ai_busy") and self._ai_busy:
            self._append_transcript_line("系统", "⏳ AI 正在处理上一个请求，请稍候...")
            return
        self._ai_busy = True

        self._append_transcript_line("系统", "🤔 AI 正在分析需求并制定执行计划...")
        self.root.update_idletasks()

        def emit(line: str) -> None:
            self.root.after(0, self._append_transcript_line, "轨迹", line)

        def _done(result, error):
            self._ai_busy = False
            if error:
                self._append_transcript_line("系统", error)
            else:
                self._append_transcript_line("AI", result)
            session.updated_at = _now_iso()
            self.manager.save_state()
            self._refresh_session_list()
            self._show_active_session()

        def _run():
            try:
                res = session.agent.handle_user_input_verbose(raw_text, event_callback=emit)
                self.root.after(0, _done, res.final_answer, None)
            except Exception as exc:
                import traceback
                err = f"❌ 系统执行异常：{exc}\n\n{traceback.format_exc()}"
                self.root.after(0, _done, None, err)

        import threading
        t = threading.Thread(target=_run, daemon=True)
        t.start()

    def _append_transcript_line(self, role: str, text: str) -> None:
        # 支持显示用户/AI/系统/轨迹等类型的信息
        allowed = {"用户", "AI", "系统", "轨迹"}
        if role not in allowed:
            return
        self.transcript.configure(state="normal")
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.transcript.insert(tk.END, f"[{timestamp}] {role}\n{text.strip()}\n\n")
        self.transcript.see(tk.END)
        self.transcript.configure(state="disabled")

    def _render_session(self, session: WorkspaceSession) -> None:
        self.transcript.configure(state="normal")
        self.transcript.delete("1.0", tk.END)
        for message in session.agent.memory.messages:
            if message.role == "system":
                continue  # 跳过系统提示词，太长
            if message.role == "tool":
                continue  # 跳过工具原始输出
            label = {
                "user": "用户",
                "assistant": "AI",
                "system": "系统",
            }.get(message.role)
            if label is None:
                continue
            self.transcript.insert(tk.END, f"[{message.timestamp}] {label}\n{message.content.strip()}\n\n")
        self.transcript.see(tk.END)
        self.transcript.configure(state="disabled")
        self.status_var.set(
            f"当前会话：{session.title} ({session.session_id}) | 消息数：{session.message_count} | 设置：provider={self.manager.settings.get('model_provider')} port={self.manager.settings.get('port')}"
        )

    def _refresh_session_list(self) -> None:
        sessions = self.manager.list_sessions()
        self.session_list.delete(0, tk.END)
        for session in sessions:
            marker = "* " if session.session_id == self.manager.active_session_id else "  "
            self.session_list.insert(tk.END, f"{marker}{session.title} [{session.session_id}]")

    def _show_active_session(self) -> None:
        session = self.manager.active_session()
        self._render_session(session)
        self._refresh_session_list()
        sessions = self.manager.list_sessions()
        for idx, item in enumerate(sessions):
            if item.session_id == session.session_id:
                self.session_list.selection_clear(0, tk.END)
                self.session_list.selection_set(idx)
                self.session_list.activate(idx)
                break

    def _selected_session_id(self) -> str | None:
        selection = self.session_list.curselection()
        if not selection:
            return None
        sessions = self.manager.list_sessions()
        index = selection[0]
        if index >= len(sessions):
            return None
        return sessions[index].session_id

    def _new_session(self) -> None:
        title = simpledialog.askstring("新建会话", "请输入会话标题（可留空）", parent=self.root)
        session = self.manager.create_session(title=title.strip() if title else None)
        self._refresh_session_list()
        self._show_active_session()
        self._append_transcript_line("系统", f"已新建会话：{session.title}")

    def _delete_session(self) -> None:
        session_id = self._selected_session_id() or self.manager.active_session_id
        if not session_id:
            return
        session = self.manager.sessions.get(session_id)
        if session is None:
            return
        if not messagebox.askyesno("删除会话", f"确认删除会话“{session.title}”？历史文件会移入回收站。", parent=self.root):
            return
        ok, message = self.manager.delete_session(session_id)
        if not ok:
            messagebox.showerror("删除失败", message, parent=self.root)
            return
        self._append_transcript_line("系统", message)
        self._refresh_session_list()
        self._show_active_session()

    def _rename_session(self) -> None:
        session_id = self._selected_session_id() or self.manager.active_session_id
        if not session_id:
            return
        session = self.manager.sessions.get(session_id)
        if session is None:
            return
        new_title = simpledialog.askstring("重命名会话", f"新的标题（当前：{session.title}）", parent=self.root)
        if not new_title:
            return
        ok, message = self.manager.rename_session(session_id, new_title)
        if not ok:
            messagebox.showerror("重命名失败", message, parent=self.root)
            return
        self._append_transcript_line("系统", message)
        self._refresh_session_list()
        self._show_active_session()

    def _on_session_selected(self, _event: tk.Event) -> None:
        session_id = self._selected_session_id()
        if not session_id:
            return
        ok, _message = self.manager.set_active_session(session_id)
        if ok:
            self._show_active_session()

    def _on_session_open(self, _event: tk.Event) -> None:
        self._on_session_selected(_event)

    def _handle_command(self, raw_text: str) -> bool:
        stripped = raw_text.strip()
        if not stripped.startswith("/"):
            return False

        tokens = shlex.split(stripped)
        if not tokens:
            return True
        command = tokens[0].lower()

        if command == "/help":
            self._show_help()
            return True

        # 其余命令（/session, /settings）已移除——由 LLM + tool 自主处理
        # 但对于非 /help 的斜杠命令，仍会走 AI 流程，LLM 可识别并调用对应工具
        return False

    def _handle_recycle_command(self, raw_text: str) -> bool:
        """处理回收站相关命令（清空回收站）。"""
        stripped = raw_text.strip().lower()

        # 匹配 "清空回收站"、"清空回收站。"、"清空回收站！" 等
        if re.search(r"清空\s*回收站", stripped):
            self._append_transcript_line("用户", raw_text)
            # 使用 recycle_panel 的 _on_empty 逻辑
            count_before = self.recycle_panel._count_windows_recycle_bin()
            has_local = self.recycle_panel._recycle_bin_dir.exists() and any(self.recycle_panel._recycle_bin_dir.iterdir())
            if count_before == 0 and not has_local:
                self._append_transcript_line("系统", "回收站已经是空的。")
                return True

            if count_before > 0 or has_local:
                self.recycle_panel._on_empty()
                self._append_transcript_line("系统", "已清空回收站。")
                # 切换到回收站选项卡，让用户看到结果
                for i, tab_text in enumerate(self.home_notebook.tabs()):
                    if self.home_notebook.tab(i, "text") == "回收站":
                        self.home_notebook.select(i)
                        break
                self.recycle_panel._refresh()
            return True

        # 查看回收站
        if re.search(r"(查看|显示|打开|看看)\s*回收站", stripped):
            self._append_transcript_line("用户", raw_text)
            self._append_transcript_line("系统", "已切换到回收站面板，请查看。")
            for i, tab_text in enumerate(self.home_notebook.tabs()):
                if self.home_notebook.tab(i, "text") == "回收站":
                    self.home_notebook.select(i)
                    break
            self.recycle_panel._refresh()
            return True

        return False

    def _send_console_input(self) -> None:
        raw_text = self.console_input.get("1.0", tk.END).strip()
        if not raw_text:
            return
        self._clear_console_input()
        self._submit_workspace_text(raw_text)

    def _on_close(self) -> None:
        self.manager.save_state()
        self._stop_qq_webhook_server()
        self.root.destroy()

    # ── QQ Webhook ────────────────────────────────────────────────────

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
            webhook_url = f"http://127.0.0.1:{port}/qq/event"
            # 通知 QQ 面板
            if hasattr(self, "qq_panel"):
                self.qq_panel.qq_webhook_url_var.set(f"NapCat事件接收地址：{webhook_url}")
            self.qq_panel.append_qq_system_message(f"NapCat 事件接收服务已启动：{webhook_url}")
            if isinstance(preferred_port, int) and preferred_port > 0 and preferred_port != port:
                self.qq_panel.append_qq_system_message(
                    f"注意：NapCat 事件上报端口偏好为 {preferred_port}，当前监听端口为 {port}。"
                )
            # 显示两个 token 的状态（只显示后4位用于区分）
            if hasattr(self, "qq_panel"):
                send_tk = self.qq_panel.qq_managed_token_var.get().strip()
                recv_tk = self.qq_panel.qq_receive_token_var.get().strip()
                parts = []
                if send_tk:
                    parts.append(f"发送Token: ...{send_tk[-4:]}")
                else:
                    parts.append("发送Token: ⚠️ 未设置")
                if recv_tk:
                    parts.append(f"接收Token: ...{recv_tk[-4:]}")
                else:
                    parts.append("接收Token: ⚠️ 未设置")
                self.qq_panel.append_qq_system_message(" | ".join(parts))
            return

        self.qq_panel.append_qq_system_message("NapCat 事件接收服务启动失败：端口被占用。")

    def _stop_qq_webhook_server(self) -> None:
        server = self.qq_webhook_server
        self.qq_webhook_server = None
        if server is not None:
            try:
                server.shutdown()
            finally:
                server.server_close()

    # ── QQ 事件轮询 ───────────────────────────────────────────────────

    def _poll_queue(self) -> None:
        """轮询 QQ 网关事件队列并触发自动回复。"""
        try:
            while True:
                action, payload = self.response_queue.get_nowait()
                if action == "qq_gateway_event":
                    self._handle_qq_gateway_event(payload)
        except queue.Empty:
            pass
        finally:
            # 定期轮询待发送私聊
            self._poll_pending_private()
            self.root.after(200, self._poll_queue)

    def _poll_pending_private(self) -> None:
        """轮询待发送的私聊队列。"""
        if not hasattr(self, "qq_panel"):
            return
        try:
            result = self.qq_panel.tool.run({"command": "poll_pending"})
            if result.success and "发送=" in result.output:
                self.qq_status_text.set(f"轮询待回复: {result.output.strip()[:60]}")
        except Exception:
            pass

    def _handle_qq_gateway_event(self, payload: dict[str, Any]) -> None:
        """处理单个 QQ 网关事件（在后台线程中执行工具调用）。"""
        raw_event = payload.get("payload") if isinstance(payload.get("payload"), dict) else payload
        event_path = str(payload.get("path", ""))
        raw_body = str(payload.get("raw_body", ""))

        # 显示事件到状态栏
        if raw_body:
            self.qq_panel.append_qq_system_message(f"QQ事件：{event_path} | {raw_body[:80]}")
        else:
            self.qq_panel.append_qq_system_message(f"QQ事件：{event_path}")

        # 在会话记录中显示收到的消息
        try:
            event_text = raw_event.get("raw_message", raw_event.get("message", raw_event.get("text", "")))
            user_id = raw_event.get("user_id", raw_event.get("sender_id", ""))
            group_or_chat = raw_event.get("group_id", raw_event.get("chat_id", raw_event.get("user_id", "")))
            source_label = f"群/{group_or_chat}" if raw_event.get("group_id") or raw_event.get("message_type") == "group" else f"私聊/{group_or_chat}"
            # 显示接收所用的 receive_token 后缀
            recv_hint = ""
            if hasattr(self.qq_panel, "qq_receive_token_var"):
                raw = self.qq_panel.qq_receive_token_var.get().strip()
                if raw:
                    recv_hint = f" [recv:{raw[-4:]}]"
            if event_text:
                self.root.after(0, self._append_chat_message, "in", f"[{source_label}]{recv_hint} {user_id}: {event_text}")
            elif raw_body:
                self.root.after(0, self._append_chat_message, "in", f"[{source_label}] {raw_body[:100]}")
        except Exception:
            pass

        # 更新 webhook URL 状态
        if hasattr(self, "qq_panel"):
            self.root.after(0, lambda: self.qq_panel.qq_status_text.set(
                f"收到QQ事件：{event_path}，正在处理..."
            ))

        # 在后台线程中执行工具调用（避免阻塞 UI）
        def _process() -> None:
            try:
                result = self.qq_panel.tool.run({
                    "command": "handle_gateway_event",
                    "event": raw_event,
                    "raw_body": raw_body,
                })

                # 回到主线程更新 UI
                self.root.after(0, self._on_qq_event_result, result, raw_event, event_path, raw_body)
            except Exception as exc:
                import traceback
                err = f"QQ事件处理异常：{exc}\n{traceback.format_exc()}"
                self.root.after(0, lambda t=err: self.qq_panel.append_qq_system_message(t))
                self.root.after(0, lambda: self.qq_panel.qq_status_text.set(err[:200]))

        thread = threading.Thread(target=_process, daemon=True)
        thread.start()

    def _on_qq_event_result(
        self,
        result: Any,
        raw_event: dict[str, Any],
        event_path: str,
        raw_body: str,
    ) -> None:
        """在主线程中处理 QQ 事件工具调用的结果。"""
        if result.success:
            meta = result.meta if isinstance(result.meta, dict) else {}
            reply_text = str(meta.get("reply", ""))
            chat_id = str(meta.get("chat_id", ""))
            message_type = str(meta.get("message_type", ""))
            endpoint = str(meta.get("endpoint", ""))
            response_text = str(meta.get("response", ""))
            reply_source = str(meta.get("reply_source", "local"))
            reply_api_error = str(meta.get("reply_api_error", ""))

            # 在会话记录中显示回复
            if reply_text and chat_id:
                # 显示实际发送所用的 token（后半部分用于确认）
                send_token_hint = ""
                if hasattr(self.qq_panel, "qq_managed_token_var"):
                    raw = self.qq_panel.qq_managed_token_var.get().strip()
                    if raw:
                        send_token_hint = f" [send:{raw[-4:]}]"
                label = f"🤖 回复 {message_type}/{chat_id}{send_token_hint}"
                self._append_chat_message("system", f"{label}\n{reply_text}")

            parts = [f"QQ事件处理成功：{result.output}"]
            if chat_id:
                parts.append(f"目标：{message_type}/{chat_id}")
            if reply_text:
                parts.append(f"回复：{reply_text[:60]}")
            if endpoint:
                parts.append(f"接口：{endpoint}")
            if response_text:
                parts.append(f"回包：{response_text[:80]}")

            status_text = " | ".join(parts)
            self.qq_panel.append_qq_system_message(status_text)
            self.qq_panel.qq_status_text.set(status_text)

            if reply_source and reply_source != "local" and reply_api_error:
                self.qq_panel.append_qq_system_message(f"回复API未接入：{reply_api_error}")
            elif reply_text and chat_id:
                self.qq_panel.append_qq_system_message(f"回复已发送到 {message_type}/{chat_id}")
        else:
            err_text = f"QQ事件处理失败：{result.output}"
            self.qq_panel.append_qq_system_message(err_text)
            self.qq_panel.qq_status_text.set(err_text)

    def _append_chat_message(self, msg_type: str, text: str) -> None:
        """在QQ会话记录区追加消息。"""
        try:
            from datetime import datetime as _dt
            ts = _dt.now().strftime("%H:%M:%S")
            self.qq_panel.qq_chat_display.configure(state=tk.NORMAL)
            tag = "msg_in" if msg_type == "in" else "msg_out"
            prefix = "📩 接收" if msg_type == "in" else "🤖 回复"
            if msg_type == "system":
                tag = "msg_sys"
                prefix = "ℹ️ 系统"
            self.qq_panel.qq_chat_display.insert(tk.END, f"[{ts}] {prefix}\n", tag)
            self.qq_panel.qq_chat_display.insert(tk.END, f"  {text}\n\n", tag)
            self.qq_panel.qq_chat_display.see(tk.END)
            self.qq_panel.qq_chat_display.configure(state=tk.DISABLED)
        except Exception:
            pass

    def _append_system_message(self, text: str) -> None:
        """在状态栏显示系统消息。"""
        current = self.status_var.get()
        self.status_var.set(f"{current} | {text}" if current else text)


def run_workspace_app() -> None:
    workspace_dir = Path.cwd() / "workspace"
    workspace_dir.mkdir(parents=True, exist_ok=True)
    root = tk.Tk()
    try:
        apply_theme(root)
    except Exception:
        pass
    WorkspaceFileApp(root, workspace_dir)
    root.mainloop()
