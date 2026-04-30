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

    def _build_payload(self, messages: list, temperature: float) -> dict:
        """构建请求 payload，注入联网搜索参数（如启用）。"""
        payload: dict = {
            "model": self.config.model_name,
            "temperature": temperature,
            "messages": messages,
        }
        if self.config.enable_search:
            provider = self.config.model_provider
            if provider == "deepseek":
                payload["enable_search"] = True
            elif provider == "qwen":
                payload["enable_search"] = True
            elif provider == "openai":
                # OpenAI 使用 search-preview 模型系列或 web_search 工具
                # 如果模型名不含 search-preview 则不自动修改
                pass
        return payload

    def generate_step(self, messages: list[Message], tool_schemas: list[dict]) -> AgentStep:
        """调用模型并返回结构化步骤。"""
        # System prompt 由 ClawminiAgent 在构建 messages 时注入
        # 这里只负责组装 payload 发送给 API
        dict_messages = [{"role": m.role, "content": m.content} for m in messages[-30:]]
        payload = self._build_payload(dict_messages, temperature=0.2)
        data = json.dumps(payload).encode("utf-8")
        resp_data = self._post_chat(data)
        text = resp_data["choices"][0]["message"]["content"]

        # 兼容两种输出格式：
        # 1. 纯 JSON：{"thought":..., "action":..., "arguments":..., "final_answer":...}
        # 2. 非纯 JSON：Thought: ...\naction: ...\narguments: {...}
        parsed = self._parse_step(text)
        action = parsed.get("action")
        return AgentStep(
            thought=parsed.get("thought", ""),
            action=ToolCall(name=action, arguments=parsed.get("arguments", {})) if action else None,
            final_answer=parsed.get("final_answer"),
        )

    def chat_direct(self, messages: list[dict]) -> str:
        """纯聊天：直接调用 chat/completions，返回原始回复文本。"""
        payload = self._build_payload(messages, temperature=0.7)
        data = json.dumps(payload).encode("utf-8")
        resp_data = self._post_chat(data)
        return resp_data["choices"][0]["message"]["content"]

    def _post_chat(self, data: bytes) -> dict:
        """发送请求到 chat/completions 并返回解析后的 JSON。"""
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
            return json.loads(resp.read().decode("utf-8"))

    @staticmethod
    def _parse_step(text: str) -> dict:
        """兼容解析 LLM 返回的步骤文本。"""
        import re as _re

        text = text.strip()

        # 尝试纯 JSON 解析（包含 ```json 标记的也剥掉）
        cleaned = text
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
            cleaned = cleaned.strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

        # 非纯 JSON 格式：逐行解析 key: value
        result: dict = {"thought": "", "action": None, "arguments": {}, "final_answer": None}
        current_key = None
        lines = text.split("\n")
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if not line:
                i += 1
                continue

            # 尝试匹配 key: value 或 key：value 格式
            key_match = _re.match(r"^(Thought|thought|action|arguments|final_answer|final_answer)\s*[：:]\s*(.*)", line)
            if key_match:
                key = key_match.group(1).lower()
                val = key_match.group(2).strip()

                if key == "thought":
                    result["thought"] = val
                elif key == "action":
                    if val and val.lower() != "none" and val.lower() != "null":
                        result["action"] = val
                    else:
                        result["action"] = None
                elif key == "arguments":
                    # arguments 可能是多行 JSON
                    arg_lines = [val] if val and val != "{}" else []
                    j = i + 1
                    # 看后续行，找到第一个 { 到匹配的 }
                    combined = " ".join(arg_lines)
                    for j in range(i + 1, len(lines)):
                        next_line = lines[j].strip()
                        combined += " " + next_line
                        if next_line and next_line[0] == "{" and "}" in combined:
                            break
                        # 如果下一行又是 key: 格式，退出
                        if _re.match(r"^(Thought|thought|action|arguments|final_answer|final_answer)\s*[：:]\s*", next_line):
                            j -= 1
                            break
                    # 尝试从 combined 中提取 JSON
                    json_match = _re.search(r"\{.*\}", combined, flags=_re.DOTALL)
                    if json_match:
                        try:
                            result["arguments"] = json.loads(json_match.group())
                        except json.JSONDecodeError:
                            result["arguments"] = {"prompt": combined}
                    elif val:
                        result["arguments"] = {"prompt": val}
                elif key == "final_answer":
                    result["final_answer"] = val if val else None
                current_key = key
            else:
                # 不是 key: value 行，如果是 arguments 的多行内容则追加
                if current_key == "arguments":
                    # 尝试找到 JSON 对象
                    json_match = _re.search(r"\{.*\}", result.get("arguments", {}), flags=_re.DOTALL)
                    if not json_match:
                        pass  # 已在上一个 key 处理中跨行消化
                elif current_key == "thought":
                    result["thought"] += " " + line

            i += 1

        return result
