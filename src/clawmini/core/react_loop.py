"""ReAct 循环模块。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from clawmini.core.memory import ConversationMemory
from clawmini.models.base import BaseModelClient
from clawmini.tools.registry import ToolRegistry


@dataclass(slots=True)
class ReactRunResult:
    """ReAct 执行结果。"""

    final_answer: str
    rounds: int
    traces: list[str]


class ReactLoop:
    """基础 ReAct 循环：Thought -> Action -> Observation。"""

    def __init__(self, model_client: BaseModelClient, tool_registry: ToolRegistry, max_rounds: int = 6) -> None:
        self.model_client = model_client
        self.tool_registry = tool_registry
        self.max_rounds = max_rounds

    def run(self, memory: ConversationMemory, event_callback: Callable[[str], None] | None = None) -> ReactRunResult:
        """执行多轮推理与工具调用。"""
        traces: list[str] = []

        def emit(line: str) -> None:
            traces.append(line)
            if event_callback is not None:
                event_callback(line)

        for round_idx in range(1, self.max_rounds + 1):
            step = self.model_client.generate_step(
                messages=memory.messages,
                tool_schemas=self.tool_registry.describe_tools(),
            )
            memory.add("assistant", f"Thought: {step.thought}")
            emit(f"Round {round_idx} Thought: {step.thought}")

            if step.final_answer:
                memory.add("assistant", step.final_answer)
                emit(f"Round {round_idx} Final: {step.final_answer}")
                return ReactRunResult(final_answer=step.final_answer, rounds=round_idx, traces=traces)

            if step.action is None:
                fallback = "我暂时无法继续规划动作，请提供更明确的信息。"
                memory.add("assistant", fallback)
                emit(f"Round {round_idx} Final: {fallback}")
                return ReactRunResult(final_answer=fallback, rounds=round_idx, traces=traces)

            emit(
                "Round "
                f"{round_idx} Action: {step.action.name}({step.action.arguments})"
            )

            result = self.tool_registry.execute(step.action)
            observation = f"Observation(success={result.success}): {result.output}"
            memory.add("tool", observation)
            emit(f"Round {round_idx} {observation}")

        stop_msg = f"已达到最大轮数 {self.max_rounds}，请拆分任务后重试。"
        memory.add("assistant", stop_msg)
        emit(f"Final: {stop_msg}")
        return ReactRunResult(final_answer=stop_msg, rounds=self.max_rounds, traces=traces)
