from pathlib import Path

from clawmini.config import AgentConfig
from clawmini.core.agent import ClawminiAgent


def test_main_agent_delegate_to_file_sub_agent(tmp_path: Path) -> None:
    target = tmp_path / "notes.md"
    target.write_text("# 标题\n\n正文", encoding="utf-8")

    config = AgentConfig(
        model_provider="mock",
        workspace_dir=tmp_path,
        history_path=tmp_path / "history.json",
        max_rounds=4,
    )
    agent = ClawminiAgent(config)

    result = agent.handle_user_input_verbose(f"分析文件 {target}")

    assert "文件分析结果" in result.final_answer
    assert result.rounds == 0
