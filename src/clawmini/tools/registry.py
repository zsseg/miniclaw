"""工具注册中心。"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Callable, TypeVar

from clawmini.tools.base import BaseTool
from clawmini.types import ToolCall, ToolResult


ToolT = TypeVar("ToolT", bound=type[BaseTool])
TOOL_CLASS_REGISTRY: dict[str, type[BaseTool]] = {}


def tool_plugin(name: str) -> Callable[[ToolT], ToolT]:
    """装饰器：注册工具类为插件。

    使用方式：
        @tool_plugin("run_shell_command")
        class ShellCommandTool(BaseTool): ...
    """

    def decorator(cls: ToolT) -> ToolT:
        TOOL_CLASS_REGISTRY[name] = cls
        return cls

    return decorator


class ToolRegistry:
    """用于注册、描述与执行工具。"""

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """注册工具。"""
        self._tools[tool.name] = tool

    def register_plugin(self, plugin_name: str, workspace_dir: Path) -> None:
        """按插件名注册工具（装饰器方式）。"""
        cls = TOOL_CLASS_REGISTRY.get(plugin_name)
        if cls is None:
            raise ValueError(f"未找到插件：{plugin_name}")
        self.register(cls(workspace_dir=workspace_dir))

    def load_from_config(self, config_path: Path, workspace_dir: Path) -> int:
        """从 JSON 配置加载工具插件。

        配置示例:
        {
          "tools": [
            {"plugin": "run_shell_command", "enabled": true},
            {"class": "clawmini.tools.shell_tool.ShellCommandTool", "enabled": true}
          ]
        }
        """
        if not config_path.exists():
            return 0
        raw = json.loads(config_path.read_text(encoding="utf-8"))
        tools = raw.get("tools", [])
        loaded = 0
        for item in tools:
            if not item.get("enabled", True):
                continue
            if "plugin" in item:
                self.register_plugin(str(item["plugin"]), workspace_dir)
                loaded += 1
                continue
            class_path = item.get("class")
            if class_path:
                module_name, class_name = str(class_path).rsplit(".", 1)
                module = importlib.import_module(module_name)
                tool_cls = getattr(module, class_name)
                self.register(tool_cls(workspace_dir=workspace_dir))
                loaded += 1
        return loaded

    def describe_tools(self) -> list[dict]:
        """返回所有工具 schema。"""
        return [tool.schema() for tool in self._tools.values()]

    def execute(self, call: ToolCall) -> ToolResult:
        """执行工具调用，统一捕获异常。"""
        tool = self._tools.get(call.name)
        if tool is None:
            return ToolResult(success=False, output=f"工具不存在：{call.name}")

        try:
            return tool.run(call.arguments)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(success=False, output=f"工具执行异常：{exc}")
