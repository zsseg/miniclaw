"""会话管理工具：让 LLM 自主创建、切换、删除、重命名、列出会话。"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from clawmini.tools.base import BaseTool
from clawmini.tools.registry import tool_plugin
from clawmini.types import ToolResult


@tool_plugin("workspace_session")
class SessionManagerTool(BaseTool):
    """会话管理工具：创建、切换、删除、重命名、列出会话。"""

    name = "workspace_session"
    description = "管理工作区会话：创建新会话、切换当前会话、删除会话、重命名会话、列出所有会话"

    parameters_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "enum": ["list", "create", "switch", "delete", "rename"],
                "description": "操作类型",
            },
            "session_id": {
                "type": "string",
                "description": "会话ID（switch/delete/rename 时需要）",
            },
            "title": {
                "type": "string",
                "description": "会话标题（create/rename 时需要）",
            },
        },
        "required": ["command"],
    }

    def __init__(self, workspace_dir: Path) -> None:
        super().__init__(workspace_dir)
        # 由 ClawminiAgent 在注册时注入
        self._session_manager: Any = None

    def set_session_manager(self, mgr: Any) -> None:
        """注入 WorkspaceSessionManager 实例。"""
        self._session_manager = mgr

    def run(self, arguments: dict[str, Any], progress_callback: Callable[[str], None] | None = None) -> ToolResult:
        command = str(arguments.get("command", "")).strip().lower()
        mgr = self._session_manager

        if command == "list":
            sessions = mgr.list_sessions()
            lines = [f"- {s.title} [{s.session_id}] (消息数={s.message_count})" for s in sessions]
            return ToolResult(True, f"共 {len(sessions)} 个会话：\n" + "\n".join(lines) if lines else "当前无会话。")

        if command == "create":
            title = str(arguments.get("title", "")).strip() or None
            session = mgr.create_session(title=title)
            return ToolResult(True, f"✅ 已创建新会话：{session.title} [{session.session_id}]")

        if command == "switch":
            session_id = str(arguments.get("session_id", "")).strip()
            if not session_id:
                return ToolResult(False, "switch 需要 session_id")
            ok, message = mgr.set_active_session(session_id)
            return ToolResult(ok, message)

        if command == "delete":
            session_id = str(arguments.get("session_id", "")).strip()
            if not session_id:
                return ToolResult(False, "delete 需要 session_id")
            ok, message = mgr.delete_session(session_id)
            return ToolResult(ok, message)

        if command == "rename":
            session_id = str(arguments.get("session_id", "")).strip()
            title = str(arguments.get("title", "")).strip()
            if not session_id or not title:
                return ToolResult(False, "rename 需要 session_id 和 title")
            ok, message = mgr.rename_session(session_id, title)
            return ToolResult(ok, message)

        return ToolResult(False, f"不支持的 command：{command}")
