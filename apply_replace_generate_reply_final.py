#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""最终定点替换 _generate_reply_via_api，彻底禁止 DeepSeek 收到 image_url。

这版不再“插入几行”，而是直接替换整个 _generate_reply_via_api。
原因：你现在报错说明旧分支仍然把 content list 传给了 DeepSeek。
"""

from __future__ import annotations

import ast
from pathlib import Path

PROJECT_ROOT = Path.cwd()
TARGET = PROJECT_ROOT / "src" / "clawmini" / "tools" / "qq_auto_reply.py"

NEW_BUILD_USER_CONTENT = '\n    def _build_user_content(self, text: str, context_info: dict[str, Any]) -> str | list[dict[str, Any]]:\n        """构造发给回复模型的用户内容。\n\n        DeepSeek：永远只返回纯文本。\n        Qwen/OpenAI vision：可以返回 content list。\n        """\n        image_refs: list[str] = []\n        seen_refs: set[str] = set()\n\n        for item in context_info.get("image_refs", []):\n            ref = str(item).strip()\n            if not ref or ref in seen_refs:\n                continue\n            seen_refs.add(ref)\n            image_refs.append(ref)\n\n        def _clean_user_text_for_image(raw: str) -> str:\n            cleaned = str(raw or "")\n            cleaned = re.sub(r"\\[CQ:image[^\\]]*\\]", "", cleaned)\n            cleaned = re.sub(r"\\[CQ:at[^\\]]*\\]", "", cleaned)\n            cleaned = cleaned.replace("[图片]", "").replace("图片消息", "")\n            cleaned = re.sub(r"\\s+", " ", cleaned).strip()\n            return cleaned\n\n        if self.enable_image_recognition and image_refs:\n            provider = self.reply_api_provider.strip().lower()\n            base_text = _clean_user_text_for_image(text)\n\n            if provider == "deepseek":\n                descriptions = self._describe_images_with_qwen_vl(image_refs, base_text)\n                clean_descriptions: list[str] = []\n                forbidden_bits = [\n                    "请识别这张 QQ 聊天图片",\n                    "如果是表情包/梗图",\n                    "如果是截图",\n                    "如果是普通图片",\n                    "用中文回答，直接描述图片内容，不要客套",\n                    "用户配文：",\n                    "请基于上面的图片内容",\n                    "请自然说明你暂时没看清图片",\n                    "【图片内容解析",\n                    "〖图片内容解析",\n                    "【图片提示】",\n                    "〖图片提示〗",\n                    "来自 Qwen-VL",\n                ]\n\n                for item in descriptions:\n                    desc = str(item or "").strip()\n                    if not desc:\n                        continue\n                    if "识别失败" in desc:\n                        continue\n                    if any(bit in desc for bit in forbidden_bits):\n                        continue\n                    clean_descriptions.append(desc)\n\n                if clean_descriptions:\n                    image_block = "\\n".join(f"- {item}" for item in clean_descriptions)\n                    if base_text:\n                        return f"{base_text}\\n\\n图片内容：\\n{image_block}"\n                    return f"用户发送了图片。\\n\\n图片内容：\\n{image_block}"\n\n                if base_text:\n                    return f"{base_text}\\n\\n图片内容：暂时无法识别清楚。"\n                return "用户发送了一张图片，但图片内容暂时无法识别清楚。"\n\n            image_hints: list[str] = []\n            for ref in image_refs:\n                img_type = self._classify_image_type(ref)\n                image_hints.append(f"[附带的{img_type}]")\n\n            annotated_text = base_text or "用户发送了图片。"\n            if image_hints:\n                annotated_text = annotated_text + "\\n\\n图片附件：" + "；".join(image_hints)\n\n            content: list[dict[str, Any]] = [{"type": "text", "text": annotated_text}]\n            for ref in image_refs:\n                image_part = self._image_ref_to_content_part(ref)\n                if image_part is not None:\n                    content.append(image_part)\n\n            if len(content) > 1:\n                return content\n\n            return annotated_text\n\n        return text\n'
NEW_GENERATE_REPLY = '\n    def _generate_reply_via_api(self, text: str, context_info: dict[str, Any] | None = None) -> str | None:\n        context_info = context_info or {}\n        provider = self.reply_api_provider.strip().lower()\n        api_key = self.reply_api_key.strip()\n\n        if provider not in {"openai", "deepseek", "qwen"} or not api_key:\n            self.last_reply_api_error = "未配置可用的回复 API（provider 或 api_key 缺失）"\n            return None\n        if not api_key.isascii():\n            self.last_reply_api_error = "API Key 含有非 ASCII 字符，请只填写真实 key，不要把说明文字一起粘贴进来"\n            return None\n\n        has_image_refs = bool(context_info.get("image_refs"))\n\n        if self.reply_api_model.strip():\n            model_name = self.reply_api_model.strip()\n        elif provider == "deepseek":\n            model_name = "deepseek-v4-pro"\n        elif provider == "qwen":\n            model_name = "qwen-vl-plus" if has_image_refs else "qwen-plus"\n        elif provider == "openai":\n            model_name = "gpt-4o" if has_image_refs else "gpt-4o-mini"\n        else:\n            model_name = "gpt-4o-mini"\n\n        base_url = self.reply_api_base_url.strip()\n        if provider == "deepseek" and not base_url:\n            base_url = "https://api.deepseek.com"\n        if provider == "deepseek" and base_url.rstrip("/").endswith("/v1"):\n            base_url = base_url.rstrip("/")[:-3].rstrip("/")\n        if provider == "openai" and not base_url:\n            base_url = "https://api.openai.com/v1"\n        if provider == "qwen" and not base_url:\n            base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"\n\n        endpoint = base_url.rstrip("/") + "/chat/completions"\n        self.last_reply_api_endpoint = endpoint\n\n        _, instructions = self._extract_instruction_from_text(text)\n        tone = instructions.get("tone", "")\n        action = instructions.get("action", "")\n\n        context_block = self._build_context_block(text, context_info)\n\n        system_prompt = (\n            "你是 QQ 聊天里的自然回复助手。"\n            "回复要短、自然、像真人群友，不要写文章。"\n            "不要输出 Markdown、标题、编号、解释性前言。"\n            "群聊里要结合上下文，合并共同话题，不要逐条复读。"\n            "如果有图片内容，就直接基于图片内容自然接话。"\n        )\n\n        if self.custom_prompt:\n            custom = self.custom_prompt.strip()\n            system_prompt += f"\\n\\n### 最高优先级人设\\n{custom}"\n        if tone:\n            system_prompt += f"\\n\\n### 语气指令\\n用户要求回复语气：{tone}"\n        if action:\n            system_prompt += f"\\n\\n### 操作指令\\n用户要求执行操作：{action}"\n        if context_block:\n            system_prompt += f"\\n\\n### 当前上下文\\n{context_block}"\n\n        user_msg = f"收到的消息：{text}\\n\\n请结合上下文给出回复。"\n        user_content = self._build_user_content(user_msg, context_info)\n\n        def _content_to_text(value: Any) -> str:\n            if isinstance(value, list):\n                parts: list[str] = []\n                for part in value:\n                    if not isinstance(part, dict):\n                        continue\n                    part_type = str(part.get("type", "")).lower()\n                    if part_type == "text":\n                        parts.append(str(part.get("text", "") or ""))\n                    elif part_type in {"image_url", "input_image"}:\n                        parts.append("[图片]")\n                    else:\n                        parts.append(f"[{part_type}]")\n                return "\\n".join(p for p in parts if p).strip() or "[图片]"\n            if value is None:\n                return ""\n            return str(value)\n\n        # 关键：DeepSeek messages[].content 必须是纯文本，绝不能是 image_url/list。\n        if provider == "deepseek":\n            user_content = _content_to_text(user_content)\n            system_prompt = _content_to_text(system_prompt)\n\n        payload: dict[str, Any] = {\n            "model": model_name,\n            "messages": [\n                {"role": "system", "content": system_prompt},\n                {"role": "user", "content": user_content},\n            ],\n        }\n\n        if provider == "deepseek":\n            # 二次保险：发出前再强制纯文本化，防止任何分支又塞回 list。\n            for msg in payload.get("messages", []):\n                if isinstance(msg, dict):\n                    msg["content"] = _content_to_text(msg.get("content"))\n\n            if model_name.startswith("deepseek-v4"):\n                payload["thinking"] = {"type": "enabled"}\n                payload["reasoning_effort"] = "high"\n                payload["max_tokens"] = 500\n            else:\n                payload["temperature"] = 0.2\n        else:\n            temperature = 0.1\n            if has_image_refs:\n                temperature = 0.2\n            if tone:\n                temperature = 0.3\n            payload["temperature"] = temperature\n\n        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")\n\n        req = urllib.request.Request(\n            endpoint,\n            data=data,\n            headers={\n                "Authorization": f"Bearer {api_key}",\n                "Content-Type": "application/json",\n            },\n            method="POST",\n        )\n\n        try:\n            with urllib.request.urlopen(req, timeout=60) as resp:\n                body = json.loads(resp.read().decode("utf-8"))\n\n            msg = body.get("choices", [{}])[0].get("message", {})\n            content = str(msg.get("content", "") or "").strip()\n            reasoning = str(msg.get("reasoning_content", "") or "").strip()\n\n            if provider == "deepseek" and model_name.startswith("deepseek-v4"):\n                print("========== DeepSeek Thinking 检测 ==========")\n                print("模型：", model_name)\n                print("thinking 参数：", payload.get("thinking"))\n                print("reasoning_effort：", payload.get("reasoning_effort"))\n                if reasoning:\n                    print(f"✅ 思考模式已开启，reasoning_content 长度：{len(reasoning)} 字符")\n                else:\n                    print("⚠️ 没检测到 reasoning_content，可能没开成功，或接口没有返回该字段")\n                print("==========================================")\n\n            self.last_reply_api_source = provider\n            self.last_reply_api_error = ""\n            return content\n\n        except urllib.error.HTTPError as exc:\n            body = exc.read().decode("utf-8", errors="replace")\n            self.last_reply_api_error = f"HTTP {exc.code} {exc.reason} | {body[:2000]}"\n            print("DeepSeek 请求失败：", self.last_reply_api_error)\n            return None\n        except Exception as exc:\n            self.last_reply_api_error = str(exc)\n            print("DeepSeek 请求失败：", exc)\n            return None\n'


def method_range(src: str, method_name: str) -> tuple[int, int]:
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == method_name:
            if node.end_lineno is None:
                raise RuntimeError("AST 没有 end_lineno")
            return node.lineno, node.end_lineno
    raise RuntimeError(f"找不到方法：{method_name}")


def replace_method(src: str, method_name: str, new_method: str) -> str:
    start, end = method_range(src, method_name)
    lines = src.splitlines()
    new_lines = lines[: start - 1] + new_method.strip("\n").splitlines() + lines[end:]
    return "\n".join(new_lines) + "\n"


def add_urllib_error_import(src: str) -> str:
    if "import urllib.error" in src:
        return src
    if "import urllib.request" in src:
        return src.replace("import urllib.request", "import urllib.request\nimport urllib.error", 1)
    return "import urllib.error\n" + src


def remove_deepseek_thinking_from_qwen_vl(src: str) -> str:
    start, end = method_range(src, "_describe_images_with_qwen_vl")
    lines = src.splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        in_method = (start - 1) <= i < end
        line = lines[i]
        stripped = line.strip()

        if in_method and stripped == "# DeepSeek V4 thinking mode: enabled":
            base_indent = len(line) - len(line.lstrip())
            i += 1
            while i < len(lines):
                nxt = lines[i]
                nxt_stripped = nxt.strip()
                nxt_indent = len(nxt) - len(nxt.lstrip())
                if nxt_stripped and nxt_indent <= base_indent:
                    break
                i += 1
            continue

        if in_method and (
            'payload["thinking"]' in stripped
            or "payload['thinking']" in stripped
            or 'payload["reasoning_effort"]' in stripped
            or "payload['reasoning_effort']" in stripped
        ):
            i += 1
            continue

        out.append(line)
        i += 1

    return "\n".join(out) + "\n"


def main() -> None:
    if not TARGET.exists():
        raise SystemExit(f"找不到文件：{TARGET}")

    src = TARGET.read_text(encoding="utf-8")
    backup = TARGET.with_suffix(".py.bak_replace_generate_reply_final")
    backup.write_text(src, encoding="utf-8")

    src = add_urllib_error_import(src)
    src = remove_deepseek_thinking_from_qwen_vl(src)
    src = replace_method(src, "_build_user_content", NEW_BUILD_USER_CONTENT)
    src = replace_method(src, "_generate_reply_via_api", NEW_GENERATE_REPLY)

    compile(src, str(TARGET), "exec")
    TARGET.write_text(src, encoding="utf-8")

    print("✅ 已最终修复：DeepSeek 主回复不会再收到 image_url/list content")
    print("已替换：_generate_reply_via_api")
    print("已修复：_build_user_content")
    print("已清理：Qwen-VL 里的 DeepSeek thinking 参数")
    print(f"备份文件：{backup}")
    print("下一步：")
    print("  python -m py_compile .\\src\\clawmini\\tools\\qq_auto_reply.py")
    print("  python app.py")


if __name__ == "__main__":
    main()
