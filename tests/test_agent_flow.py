from pathlib import Path

from clawmini.config import AgentConfig
from clawmini.core.agent import ClawminiAgent


def test_agent_with_mock_model_runs_tool(tmp_path: Path) -> None:
    config = AgentConfig(
        model_provider="mock",
        workspace_dir=tmp_path,
        history_path=tmp_path / "history.json",
        max_rounds=4,
    )
    agent = ClawminiAgent(config)

    answer = agent.handle_user_input("请帮我写一篇关于人工智能伦理的文稿，800字，保存为 ethics.md")

    assert "Observation" in answer
    assert (tmp_path / "article_auto.md").exists()
