"""DeepSeek 模型适配（OpenAI 兼容协议）。"""

from __future__ import annotations

from clawmini.config import AgentConfig
from clawmini.models.openai_model import OpenAIModelClient


class DeepSeekModelClient(OpenAIModelClient):
    """DeepSeek 客户端。

    DeepSeek 提供 OpenAI 兼容 API，因此复用 OpenAI 适配逻辑。
    """

    def __init__(self, config: AgentConfig) -> None:
        adapted = AgentConfig(
            model_provider="deepseek",
            model_name=config.model_name or "deepseek-chat",
            api_key=config.api_key,
            base_url=config.base_url or "https://api.deepseek.com/v1",
            max_rounds=config.max_rounds,
            workspace_dir=config.workspace_dir,
            history_path=config.history_path,
            quiet_mode=config.quiet_mode,
        )
        super().__init__(adapted)
