"""智能体总控模块：装配模型、工具与 ReAct。"""

from __future__ import annotations

import re
from typing import Callable

from clawmini.config import AgentConfig
from clawmini.core.memory import ConversationMemory
from clawmini.core.react_loop import ReactLoop, ReactRunResult
from clawmini.core.sub_agents import FileAnalysisAgent
from clawmini.models.base import BaseModelClient
from clawmini.models.deepseek_model import DeepSeekModelClient
from clawmini.models.mock_model import MockModelClient
from clawmini.models.openai_model import OpenAIModelClient
from clawmini.storage.history_store import HistoryStore
from clawmini.tools.image_batch_tool import ImageBatchTool
from clawmini.tools.qq_auto_reply import QQAutoReplyTool
from clawmini.tools.registry import ToolRegistry
from clawmini.tools.shell_tool import ShellCommandTool
from clawmini.tools.writing_tool import WritingTool


class ClawminiAgent:
    """Clawmini 智能体。"""

    def __init__(self, config: AgentConfig) -> None:
        self.config = config
        self.config.ensure_workspace()

        self.memory = ConversationMemory()
        self.history_store = HistoryStore(config.history_path)
        self.memory.messages.extend(self.history_store.load())
        self.file_analysis_agent = FileAnalysisAgent(workspace_dir=config.workspace_dir)

        self.registry = ToolRegistry()
        self._register_tools()

        self.model_client = self._build_model_client()
        self.react_loop = ReactLoop(self.model_client, self.registry, max_rounds=config.max_rounds)

    def _register_tools(self) -> None:
        """注册业务工具。"""
        self.registry.register(QQAutoReplyTool(workspace_dir=self.config.workspace_dir))
        self.registry.register(WritingTool(workspace_dir=self.config.workspace_dir))
        self.registry.register(ImageBatchTool(workspace_dir=self.config.workspace_dir))
        self.registry.register(ShellCommandTool(workspace_dir=self.config.workspace_dir))
        if self.config.tool_plugins_config is not None:
            self.registry.load_from_config(self.config.tool_plugins_config, workspace_dir=self.config.workspace_dir)

    def _build_model_client(self) -> BaseModelClient:
        """根据配置构造模型客户端。"""
        provider = self.config.model_provider
        if provider == "openai":
            return OpenAIModelClient(self.config)
        if provider == "deepseek":
            return DeepSeekModelClient(self.config)
        return MockModelClient()

    def handle_user_input(self, user_text: str) -> str:
        """处理用户输入并返回最终回答。"""
        result = self.handle_user_input_verbose(user_text)
        return result.final_answer

    def handle_user_input_verbose(
        self,
        user_text: str,
        event_callback: Callable[[str], None] | None = None,
    ) -> ReactRunResult:
        """处理用户输入并返回完整轨迹。"""
        self.memory.add("user", user_text)
        delegated = self._try_delegate(user_text)
        if delegated is not None:
            self.memory.add("assistant", delegated)
            result = ReactRunResult(final_answer=delegated, rounds=0, traces=["SubAgent delegated: file-analysis"])
            if event_callback is not None:
                event_callback(result.traces[0])
            self.history_store.save(self.memory.messages)
            return result

        result = self.react_loop.run(self.memory, event_callback=event_callback)
        self.history_store.save(self.memory.messages)
        return result

    def _try_delegate(self, user_text: str) -> str | None:
        """主 Agent 委托子 Agent（雏形）。"""
        match = re.search(r"分析文件\s+(.+)$", user_text.strip())
        if not match:
            return None
        raw_path = match.group(1).strip().strip("\"'")
        return self.file_analysis_agent.analyze_file(raw_path)
