"""安全 Shell 工具：提供白名单命令执行能力。"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

from clawmini.core.security import ensure_path_in_workspace
from clawmini.tools.base import BaseTool
from clawmini.tools.registry import tool_plugin
from clawmini.types import ToolResult


@tool_plugin("run_shell_command")
class ShellCommandTool(BaseTool):
    """受限命令执行工具。

    安全策略：
    - 命令白名单
    - 参数危险字符拦截
    - 不使用 shell=True
    - 执行目录限制在 workspace
    """

    name = "run_shell_command"
    description = "在安全沙箱中执行白名单 shell 命令"
    parameters_schema = {
        "type": "object",
        "properties": {
            "command": {"type": "string"},
            "args": {"type": "array", "items": {"type": "string"}},
            "cwd": {"type": "string"},
            "timeout_sec": {"type": "integer"},
        },
        "required": ["command"],
    }

    ALLOWED_COMMANDS = {"python", "dir", "echo", "type", "findstr"}
    DANGEROUS_PATTERN = re.compile(r"[;&|><`$]")
    MAX_ARGS = 12
    MAX_ARG_LENGTH = 200

    def run(self, arguments: dict[str, Any], progress_callback: Callable[[str], None] | None = None) -> ToolResult:
        command = str(arguments.get("command", "")).strip().lower()
        args = arguments.get("args", [])
        timeout_sec = int(arguments.get("timeout_sec", 10))

        if command not in self.ALLOWED_COMMANDS:
            return ToolResult(False, f"命令不在白名单内：{command}")
        if not isinstance(args, list) or not all(isinstance(a, str) for a in args):
            return ToolResult(False, "args 必须是字符串数组")
        if len(args) > self.MAX_ARGS:
            return ToolResult(False, f"参数数量过多，最多允许 {self.MAX_ARGS} 个")
        if any(len(a) > self.MAX_ARG_LENGTH for a in args):
            return ToolResult(False, f"单个参数过长，最大长度 {self.MAX_ARG_LENGTH}")
        if any(self.DANGEROUS_PATTERN.search(a) for a in args):
            return ToolResult(False, "检测到高风险参数字符，已拒绝执行")
        if timeout_sec < 1 or timeout_sec > 30:
            return ToolResult(False, "timeout_sec 必须在 1 到 30 秒之间")

        validation_err = self._validate_args(command, args)
        if validation_err:
            return ToolResult(False, validation_err)

        raw_cwd = str(arguments.get("cwd", "."))
        cwd_candidate = Path(raw_cwd)
        if not cwd_candidate.is_absolute():
            cwd_candidate = self.workspace_dir / cwd_candidate
        run_cwd = ensure_path_in_workspace(cwd_candidate, self.workspace_dir)

        exec_cmd = self._build_exec_command(command, args)
        try:
            proc = subprocess.run(
                exec_cmd,
                cwd=run_cwd,
                capture_output=True,
                text=True,
                timeout=timeout_sec,
                shell=False,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return ToolResult(False, f"命令执行超时（>{timeout_sec}s）")

        output = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
        output = output.strip()[:4000]
        success = proc.returncode == 0
        return ToolResult(success, output or f"命令执行完成，返回码={proc.returncode}", {"returncode": proc.returncode})

    def _build_exec_command(self, command: str, args: list[str]) -> list[str]:
        """构造可执行命令。"""
        if command == "python":
            return [sys.executable, *args]
        if command == "dir":
            # dir 为 shell 内建命令，这里使用 cmd /c dir 实现且不拼接危险字符。
            return ["cmd", "/c", "dir", *args]
        return [command, *args]

    def _validate_args(self, command: str, args: list[str]) -> str | None:
        """校验不同命令的参数规则。"""
        if command == "python":
            if not args:
                return "python 命令至少需要一个参数（如 -c）"
            if args[0] not in {"-c", "-m"}:
                return "python 仅允许 -c 或 -m 模式"
        if command in {"type", "findstr"} and args:
            if any(a.startswith("/") for a in args):
                return f"{command} 不允许使用系统开关参数"
        return None
