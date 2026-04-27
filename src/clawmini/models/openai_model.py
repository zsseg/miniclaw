"""OpenAI 模型适配（OpenAI Chat Completions 接口）。"""

from __future__ import annotations

import json
import urllib.request

from clawmini.config import AgentConfig
from clawmini.models.base import BaseModelClient
from clawmini.types import AgentStep, Message, ToolCall


class OpenAIModelClient(BaseModelClient):
    """OpenAI 兼容客户端。"""

    def __init__(self, config: AgentConfig) -> None:
        self.config = config
        if not config.api_key:
            raise ValueError("OpenAI 模式需要提供 api_key")
        self.endpoint = (config.base_url or "https://api.openai.com/v1") + "/chat/completions"

    def generate_step(self, messages: list[Message], tool_schemas: list[dict]) -> AgentStep:
        """调用模型并返回结构化步骤。"""
        system_prompt = (
            "你是 Clawmini 的规划器。你必须输出 JSON："
            "{\"thought\": str, \"action\": str|null, \"arguments\": object, \"final_answer\": str|null}。"
            "当需要调用工具时填 action 与 arguments；结束时填写 final_answer。"
        )
        payload = {
            "model": self.config.model_name,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "system",
                    "content": "可用工具: " + json.dumps(tool_schemas, ensure_ascii=False),
                },
                *[{"role": m.role, "content": m.content} for m in messages[-20:]],
            ],
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.endpoint,
            data=data,
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read().decode("utf-8"))

        text = body["choices"][0]["message"]["content"]
        parsed = json.loads(text)
        action = parsed.get("action")
        return AgentStep(
            thought=parsed.get("thought", ""),
            action=ToolCall(name=action, arguments=parsed.get("arguments", {})) if action else None,
            final_answer=parsed.get("final_answer"),
        )
