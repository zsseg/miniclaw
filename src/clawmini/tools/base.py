"""工具抽象层。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from clawmini.types import ToolResult


class BaseTool(ABC):
    """工具基类。"""

    name: str
    description: str
    parameters_schema: dict[str, Any]

    def __init__(self, workspace_dir: Path) -> None:
        self.workspace_dir = workspace_dir

    @abstractmethod
    def run(self, arguments: dict[str, Any]) -> ToolResult:
        """执行工具并返回结果。"""

    def schema(self) -> dict[str, Any]:
        """返回工具描述，供模型决策。"""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters_schema,
        }
