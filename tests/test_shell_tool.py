from pathlib import Path

from clawmini.tools.shell_tool import ShellCommandTool


def test_shell_tool_allow_python_command(tmp_path: Path) -> None:
    tool = ShellCommandTool(workspace_dir=tmp_path)
    result = tool.run(
        {
            "command": "python",
            "args": ["-c", "print('ok')"],
            "timeout_sec": 5,
        }
    )
    assert result.success
    assert "ok" in result.output


def test_shell_tool_reject_non_whitelist(tmp_path: Path) -> None:
    tool = ShellCommandTool(workspace_dir=tmp_path)
    result = tool.run({"command": "powershell", "args": ["Get-ChildItem"]})
    assert not result.success
    assert "白名单" in result.output


def test_shell_tool_reject_too_many_args(tmp_path: Path) -> None:
    tool = ShellCommandTool(workspace_dir=tmp_path)
    result = tool.run({"command": "echo", "args": ["a"] * 20})
    assert not result.success
    assert "参数数量过多" in result.output


def test_shell_tool_reject_invalid_timeout(tmp_path: Path) -> None:
    tool = ShellCommandTool(workspace_dir=tmp_path)
    result = tool.run({"command": "echo", "args": ["ok"], "timeout_sec": 100})
    assert not result.success
    assert "timeout_sec" in result.output
