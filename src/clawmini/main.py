"""命令行入口：启动 Clawmini 智能体。"""

from __future__ import annotations

from pathlib import Path

from .config import AgentConfig
from .core.agent import ClawminiAgent


def build_default_config() -> AgentConfig:
    """构造默认配置（离线可运行）。"""
    return AgentConfig(
        model_provider="mock",
        model_name="clawmini-mock",
        workspace_dir=Path.cwd() / "workspace",
        history_path=Path.cwd() / "workspace" / "history.json",
        max_rounds=6,
    )


def run_cli() -> None:
    """启动交互式命令行。"""
    config = build_default_config()
    agent = ClawminiAgent(config)
    stream_mode = config.enable_stream_output
    plan_mode = config.show_react_steps
    print("Clawmini 已启动，输入 quit 退出。可用命令：/stream on|off, /plan on|off")

    while True:
        user_input = input("你: ").strip()
        if not user_input:
            continue
        if user_input.lower() in {"quit", "exit"}:
            print("再见。")
            break

        if user_input.lower() in {"/stream on", "/stream off"}:
            stream_mode = user_input.lower().endswith("on")
            print(f"流式输出已{'开启' if stream_mode else '关闭'}。")
            continue
        if user_input.lower() in {"/plan on", "/plan off"}:
            plan_mode = user_input.lower().endswith("on")
            print(f"规划展示已{'开启' if plan_mode else '关闭'}。")
            continue

        result = agent.handle_user_input_verbose(user_input)
        if plan_mode:
            for line in result.traces:
                print(f"[规划] {line}")
        print("Clawmini: ", end="")
        if stream_mode:
            for ch in result.final_answer:
                print(ch, end="", flush=True)
            print()
        else:
            print(result.final_answer)


if __name__ == "__main__":
    run_cli()
