import json
from pathlib import Path

from clawmini.config import AgentConfig
from clawmini.core.agent import ClawminiAgent
from clawmini.tools.registry import ToolRegistry

# 确保装饰器插件已注册
import clawmini.tools.shell_tool  # noqa: F401


def test_plugin_load_from_config(tmp_path: Path) -> None:
    cfg = tmp_path / "tools_plugins.json"
    cfg.write_text(
        json.dumps(
            {
                "tools": [
                    {"plugin": "run_shell_command", "enabled": True},
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    registry = ToolRegistry()
    loaded = registry.load_from_config(cfg, workspace_dir=tmp_path)

    assert loaded == 1
    names = [tool["name"] for tool in registry.describe_tools()]
    assert "run_shell_command" in names


def test_react_traces_are_available(tmp_path: Path) -> None:
    config = AgentConfig(
        model_provider="mock",
        workspace_dir=tmp_path,
        history_path=tmp_path / "history.json",
        max_rounds=4,
    )
    agent = ClawminiAgent(config)

    result = agent.handle_user_input_verbose("你好")

    assert result.traces
    assert any("Thought" in t or "Final" in t for t in result.traces)


def test_plugin_config_file_bootstrap(tmp_path: Path) -> None:
    config = AgentConfig(
        model_provider="mock",
        workspace_dir=tmp_path,
        history_path=tmp_path / "history.json",
        tool_plugins_config=tmp_path / "plugins.json",
    )
    config.ensure_workspace()
    assert config.tool_plugins_config is not None
    assert config.tool_plugins_config.exists()
    data = json.loads(config.tool_plugins_config.read_text(encoding="utf-8"))
    assert data == {"tools": []}


def test_agent_event_callback_receives_trace(tmp_path: Path) -> None:
    config = AgentConfig(
        model_provider="mock",
        workspace_dir=tmp_path,
        history_path=tmp_path / "history.json",
        max_rounds=4,
    )
    agent = ClawminiAgent(config)
    events: list[str] = []

    _ = agent.handle_user_input_verbose("你好", event_callback=events.append)

    assert events
