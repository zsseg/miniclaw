from pathlib import Path

from clawmini.config import AgentConfig
from clawmini.core.agent import ClawminiAgent


def test_open_request_returns_multiple_plans_via_agent(tmp_path: Path) -> None:
    config = AgentConfig(
        model_provider="mock",
        workspace_dir=tmp_path,
        history_path=tmp_path / "history.json",
        max_rounds=4,
    )
    agent = ClawminiAgent(config)

    answer = agent.handle_user_input("帮我写一篇人工智能伦理的文章")

    assert "候选写作方案" in answer
    assert "方案1" in answer
