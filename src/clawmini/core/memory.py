"""会话记忆模块：维护多轮对话上下文。"""

from __future__ import annotations

from dataclasses import dataclass, field

from clawmini.types import Message, MessageRole


@dataclass(slots=True)
class ConversationMemory:
    """对话历史容器。"""

    messages: list[Message] = field(default_factory=list)

    def add(self, role: MessageRole, content: str) -> None:
        """追加一条消息。"""
        self.messages.append(Message(role=role, content=content))

    def get_recent(self, limit: int = 10) -> list[Message]:
        """获取最近 N 条消息。"""
        return self.messages[-limit:]
