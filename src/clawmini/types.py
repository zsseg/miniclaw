"""类型模块：统一定义消息、工具调用与推理步骤的数据结构。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal


MessageRole = Literal["system", "user", "assistant", "tool"]


@dataclass(slots=True)
class Message:
    """对话消息。"""

    role: MessageRole
    content: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))


@dataclass(slots=True)
class ToolCall:
    """工具调用请求。"""

    name: str
    arguments: dict[str, Any]


@dataclass(slots=True)
class AgentStep:
    """单轮推理结果。

    规则:
    - 若 `final_answer` 非空，代表本轮直接结束。
    - 若 `action` 非空，代表需要执行工具。
    """

    thought: str
    action: ToolCall | None = None
    final_answer: str | None = None


@dataclass(slots=True)
class ToolResult:
    """工具执行结果。"""

    success: bool
    output: str
    meta: dict[str, Any] = field(default_factory=dict)
