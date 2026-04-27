"""模型抽象层。"""

from __future__ import annotations

from abc import ABC, abstractmethod

from clawmini.types import AgentStep, Message


class BaseModelClient(ABC):
    """模型客户端抽象基类。"""

    @abstractmethod
    def generate_step(self, messages: list[Message], tool_schemas: list[dict]) -> AgentStep:
        """生成下一步动作或最终答案。"""
