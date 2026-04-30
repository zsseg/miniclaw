"""配置模块：定义 Clawmini 运行参数。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


ModelProvider = Literal["mock", "openai", "deepseek", "qwen"]


@dataclass(slots=True)
class AgentConfig:
    """智能体配置。

    属性:
        model_provider: 模型供应商，支持 mock/openai/deepseek。
        model_name: 模型名称。
        api_key: 模型 API Key（mock 模式可为空）。
        base_url: 可选自定义接口地址。
        max_rounds: ReAct 最大迭代轮数。
        workspace_dir: 工具可操作的根目录。
        history_path: 会话历史持久化文件。
        quiet_mode: 安静模式，启用后仅执行工具不打印中间细节。
        show_react_steps: 是否在 CLI 中显示每轮规划过程。
        enable_stream_output: 是否启用流式输出。
        tool_plugins_config: 插件工具配置文件路径（JSON）。
    """

    model_provider: ModelProvider = "mock"
    model_name: str = "clawmini-mock"
    api_key: str | None = None
    base_url: str | None = None
    max_rounds: int = 6
    workspace_dir: Path = field(default_factory=lambda: Path.cwd() / "workspace")
    history_path: Path = field(default_factory=lambda: Path.cwd() / "workspace" / "history.json")
    quiet_mode: bool = False
    show_react_steps: bool = True
    enable_stream_output: bool = True
    enable_search: bool = False
    """启用联网搜索（DeepSeek/Qwen 支持）。"""

    tool_plugins_config: Path | None = field(default_factory=lambda: Path.cwd() / "workspace" / "tools_plugins.json")

    def __post_init__(self) -> None:
        """确保 Path 类型字段始终为 Path 对象。"""
        if isinstance(self.workspace_dir, str):
            self.workspace_dir = Path(self.workspace_dir)
        if isinstance(self.history_path, str):
            self.history_path = Path(self.history_path)
        if isinstance(self.tool_plugins_config, str):
            self.tool_plugins_config = Path(self.tool_plugins_config)

    def ensure_workspace(self) -> None:
        """确保工作目录与历史文件父目录存在。"""
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        self.history_path.parent.mkdir(parents=True, exist_ok=True)
        if self.tool_plugins_config is not None:
            self.tool_plugins_config.parent.mkdir(parents=True, exist_ok=True)
            if not self.tool_plugins_config.exists():
                self.tool_plugins_config.write_text(
                    json.dumps({"tools": []}, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
