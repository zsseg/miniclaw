"""模型抽象层。"""

from __future__ import annotations

from abc import ABC, abstractmethod

from clawmini.types import AgentStep, Message


class BaseModelClient(ABC):
    """模型客户端抽象基类。"""

    @abstractmethod
    def generate_step(self, messages: list[Message], tool_schemas: list[dict]) -> AgentStep:
        """生成下一步动作或最终答案。"""

    def chat_direct(self, messages: list[dict]) -> str:
        """纯聊天：直接返回模型回复文本（无工具 schema）。
        子类可重写以支持更高效的纯聊天路径。
        """
        # 默认回退：用 generate_step 但传空 tool_schemas
        msg_objects = [Message(role=m["role"], content=m["content"]) for m in messages]
        step = self.generate_step(msg_objects, [])
        return step.final_answer or step.thought or ""
