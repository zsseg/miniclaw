"""3.2 写作工具调试入口。"""

from __future__ import annotations

from pathlib import Path

from clawmini.tools.writing_tool import WritingTool


def run_debug() -> None:
    """启动写作工具调试交互。

    支持：
    - `plan <开放式请求>`：输出 2-3 种方案
    - `create <主题>`：快速生成文稿
    - `quit`：退出
    """
    workspace = Path.cwd() / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    tool = WritingTool(workspace_dir=workspace)

    print("Writing Debug 已启动。命令: plan <请求> | create <主题> | quit")
    while True:
        raw = input("debug> ").strip()
        if not raw:
            continue
        if raw.lower() in {"quit", "exit"}:
            print("debug 结束。")
            break

        if raw.startswith("plan "):
            req = raw[5:].strip()
            result = tool.run({"command": "brainstorm_plans", "request": req, "plan_count": 3})
            print(result.output)
            continue

        if raw.startswith("create "):
            topic = raw[7:].strip()
            result = tool.run(
                {
                    "command": "create",
                    "topic": topic,
                    "word_count": 600,
                    "style": "通用",
                }
            )
            print(result.output)
            continue

        print("未知命令，请使用 plan/create/quit。")


if __name__ == "__main__":
    run_debug()
