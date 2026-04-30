"""设置管理工具：让 LLM 自主查看和修改工作区设置。"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from clawmini.tools.base import BaseTool
from clawmini.tools.registry import tool_plugin
from clawmini.types import ToolResult


@tool_plugin("workspace_settings")
class SettingsTool(BaseTool):
    """设置管理工具：查看或修改工作区的 API 提供商、模型、Key 等配置。"""

    name = "workspace_settings"
    description = "管理工作区设置：查看当前配置（show）、修改配置（update）。修改后会立即生效并重建 AI 会话引擎。"

    parameters_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "enum": ["show", "update"],
                "description": "show=查看当前设置, update=修改设置",
            },
            "model_provider": {
                "type": "string",
                "enum": ["openai", "deepseek", "qwen", "mock"],
                "description": "模型提供商",
            },
            "model_name": {
                "type": "string",
                "description": "模型名称（如 qwen-plus, deepseek-chat, gpt-4o）",
            },
            "api_key": {
                "type": "string",
                "description": "API Key",
            },
            "base_url": {
                "type": "string",
                "description": "API 基址 URL",
            },
            "port": {
                "type": "integer",
                "description": "服务端口号",
            },
            "enable_search": {
                "type": "boolean",
                "description": "启用联网搜索（true/false，仅 DeepSeek/Qwen 支持）",
            },
        },
        "required": ["command"],
    }

    def __init__(self, workspace_dir: Path) -> None:
        super().__init__(workspace_dir)
        self._session_manager: Any = None

    def set_session_manager(self, mgr: Any) -> None:
        """注入 WorkspaceSessionManager 实例。"""
        self._session_manager = mgr

    def run(self, arguments: dict[str, Any], progress_callback: Callable[[str], None] | None = None) -> ToolResult:
        command = str(arguments.get("command", "")).strip().lower()
        mgr = self._session_manager
        if mgr is None:
            return ToolResult(False, "设置工具未就绪（缺少 session manager）")

        settings = mgr.settings
        provider = str(settings.get("model_provider", "mock"))

        if command == "show":
            search_status = "已开启 🔍" if settings.get("enable_search") else "未开启"
            lines = [
                f"当前设置:",
                f"  Provider: {provider}",
                f"  Model: {settings.get('model_name', '') or '（未设置）'}",
                f"  API Key: {'已设置' if settings.get('api_key') else '未设置'}",
                f"  Base URL: {settings.get('base_url', '') or '（未设置）'}",
                f"  Port: {settings.get('port', 17888)}",
                f"  联网搜索: {search_status}",
                "",
                "各提供商独立配置:",
            ]
            pcfgs = settings.get("provider_configs", {})
            for prov, cfg in pcfgs.items():
                if isinstance(cfg, dict):
                    ak = "已设置" if cfg.get("api_key") else "未设置"
                    lines.append(f"  {prov}: model={cfg.get('model_name','')}, key={ak}, url={cfg.get('base_url','')}")
            return ToolResult(True, "\n".join(lines))

        if command == "update":
            updates: dict[str, Any] = {}
            for key in ("model_provider", "model_name", "api_key", "base_url", "port", "enable_search"):
                raw = arguments.get(key)
                if raw is None:
                    continue
                if key == "port":
                    try:
                        updates[key] = int(raw)
                    except (ValueError, TypeError):
                        return ToolResult(False, f"port 必须是整数，收到：{raw}")
                elif key == "model_provider":
                    val = str(raw).strip().lower()
                    if val not in ("openai", "deepseek", "qwen", "mock"):
                        return ToolResult(False, f"不支持的 provider：{val}（可选：openai, deepseek, qwen, mock）")
                    updates[key] = val
                elif key == "enable_search":
                    if isinstance(raw, bool):
                        updates[key] = raw
                    elif str(raw).strip().lower() in ("true", "1", "yes", "是"):
                        updates[key] = True
                    elif str(raw).strip().lower() in ("false", "0", "no", "否"):
                        updates[key] = False
                    else:
                        return ToolResult(False, f"enable_search 必须是 true/false，收到：{raw}")
                else:
                    updates[key] = str(raw).strip()

            if not updates:
                return ToolResult(False, "未提供任何要修改的设置项")

            # 记录变更摘要
            changed = ", ".join(f"{k}={updates[k]}" for k in updates)
            mgr.update_settings(updates)
            return ToolResult(True, f"✅ 设置已更新：{changed}\n新引擎已就绪，可直接使用。")

        return ToolResult(False, f"不支持的 command：{command}")
