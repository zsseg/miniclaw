"""离线 Mock 模型：基于规则模拟 Function Calling。"""

from __future__ import annotations

import re

from clawmini.models.base import BaseModelClient
from clawmini.types import AgentStep, Message, ToolCall


class MockModelClient(BaseModelClient):
    """用于本地开发与测试的规则模型。"""

    def generate_step(self, messages: list[Message], tool_schemas: list[dict]) -> AgentStep:
        """根据用户最新输入做简化推理。"""
        if messages and messages[-1].role == "tool":
            return AgentStep(thought="工具已返回结果，整理为最终回复", final_answer=messages[-1].content)

        latest_user = next((m.content for m in reversed(messages) if m.role == "user"), "")

        if any(key in latest_user for key in ["QQ", "私聊", "群", "自动回复"]):
            return AgentStep(
                thought="检测到 QQ 自动回复需求，调用 QQ 工具执行。",
                action=ToolCall(
                    name="qq_auto_reply",
                    arguments={
                        "command": "handle_message",
                        "source": "group" if "群" in latest_user else "private",
                        "chat_id": "demo_chat",
                        "sender_id": "anon_user",
                        "text": latest_user,
                        "mentioned": "@我" in latest_user,
                        "mention_all": "@所有人" in latest_user,
                    },
                ),
            )

        if any(key in latest_user for key in ["文稿", "文章", "写一篇", "写作", ".md", ".txt"]):
            has_word_target = any(ch.isdigit() for ch in latest_user)
            has_filename = ".md" in latest_user or ".txt" in latest_user
            has_style_hint = any(k in latest_user for k in ["正式", "幽默", "技术", "学术", "科普"])
            if not has_word_target and not has_filename and not has_style_hint:
                return AgentStep(
                    thought="检测到开放式写作请求，先输出 2-3 个候选方案供用户选择。",
                    action=ToolCall(
                        name="writing_tool",
                        arguments={
                            "command": "brainstorm_plans",
                            "request": latest_user,
                            "plan_count": 3,
                        },
                    ),
                )

            word_count = 800 if "800" in latest_user else 300
            return AgentStep(
                thought="检测到文稿生成请求，调用写作工具创建文件。",
                action=ToolCall(
                    name="writing_tool",
                    arguments={
                        "command": "create",
                        "topic": latest_user,
                        "style": "正式" if "正式" in latest_user else "通用",
                        "word_count": word_count,
                        "filename": "article_auto.md",
                    },
                ),
            )

        if any(key in latest_user.lower() for key in ["图片", "jpeg", "png", "resize", "批量"]):
            return AgentStep(
                thought="检测到批量图片处理请求，调用图像工具。",
                action=ToolCall(
                    name="image_batch_tool",
                    arguments={
                        "request": latest_user,
                        "input_dir": "images",
                        "output_dir": "output",
                        "target_format": "png",
                        "width": 1024,
                        "height": 768,
                        "overwrite": False,
                    },
                ),
            )

        if "shell" in latest_user.lower() or "命令" in latest_user:
            return AgentStep(
                thought="检测到命令执行请求，调用安全 shell 工具。",
                action=ToolCall(
                    name="run_shell_command",
                    arguments={
                        "command": "python",
                        "args": ["-c", "print('hello from shell tool')"],
                        "timeout_sec": 5,
                    },
                ),
            )

        if re.search(r"(你好|hi|hello)", latest_user, flags=re.IGNORECASE):
            return AgentStep(thought="常规问候，无需工具。", final_answer="你好，我是 Clawmini，可以帮你处理 QQ、文稿和图片任务。")

        return AgentStep(thought="未命中工具，直接答复。", final_answer="我已收到请求。若要执行操作，请明确说明 QQ、文稿或图片任务。")
