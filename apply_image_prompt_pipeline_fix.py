#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""彻底修复：识图后把 Qwen-VL prompt / 中间提示词发到群里。

修复当前 New_write 的 qq_auto_reply.py：
1. _build_user_content 不再返回「〖图片内容解析〗+ 请基于上面的图片内容...」这种可能被兜底回显的 prompt。
2. 它只返回干净的「用户文字 + 图片内容」。
3. _sanitize_reply_before_send 会拦截所有图片 prompt / system prompt 泄漏。
4. _send_via_gateway 开头强制 sanitize，所有发群文本都经过过滤。
"""

from __future__ import annotations

import ast
from pathlib import Path


PROJECT_ROOT = Path.cwd()
TARGET = PROJECT_ROOT / "src" / "clawmini" / "tools" / "qq_auto_reply.py"

NEW_BUILD_USER_CONTENT = '\n    def _build_user_content(self, text: str, context_info: dict[str, Any]) -> str | list[dict[str, Any]]:\n        """构造发给回复模型的用户内容。\n\n        关键修复：\n        - DeepSeek 不直接吃图，所以先用 Qwen-VL 识图。\n        - 但是绝不能把“请识别图片/请基于图片回复”这类中间提示塞进最终可能被回显的文本。\n        - 这里只返回干净的图片事实文本：用户文字 + 图片内容。\n        """\n        image_refs: list[str] = []\n        seen_refs: set[str] = set()\n\n        for item in context_info.get("image_refs", []):\n            ref = str(item).strip()\n            if not ref or ref in seen_refs:\n                continue\n            seen_refs.add(ref)\n            image_refs.append(ref)\n\n        if self.enable_image_recognition and image_refs:\n            provider = self.reply_api_provider.strip().lower()\n\n            # DeepSeek V4 不直接吃图片；先用 Qwen-VL 识图，再把“干净图片内容”交给 DeepSeek。\n            if provider == "deepseek":\n                descriptions = self._describe_images_with_qwen_vl(image_refs, text)\n\n                clean_descriptions: list[str] = []\n                forbidden_bits = [\n                    "请识别这张 QQ 聊天图片",\n                    "如果是表情包/梗图",\n                    "如果是截图",\n                    "如果是普通图片",\n                    "用中文回答，直接描述图片内容，不要客套",\n                    "用户配文：",\n                    "请基于上面的图片内容",\n                    "请自然说明你暂时没看清图片",\n                    "〖图片内容解析",\n                    "〖图片提示〗",\n                ]\n\n                for item in descriptions:\n                    desc = str(item or "").strip()\n                    if not desc:\n                        continue\n\n                    # Qwen 失败信息不拿去当正常图片内容\n                    if "识别失败" in desc:\n                        continue\n\n                    # 如果某处异常把识图 prompt 当成 description 带出来，过滤掉\n                    if any(bit in desc for bit in forbidden_bits):\n                        continue\n\n                    clean_descriptions.append(desc)\n\n                base_text = text.strip()\n                if clean_descriptions:\n                    image_block = "\\n".join(f"- {item}" for item in clean_descriptions)\n                    if base_text:\n                        return f"{base_text}\\n\\n图片内容：\\n{image_block}"\n                    return f"图片内容：\\n{image_block}"\n\n                if base_text:\n                    return f"{base_text}\\n\\n图片内容：暂时无法识别清楚。"\n                return "用户发送了一张图片，但图片内容暂时无法识别清楚。"\n\n            # Qwen/OpenAI 这类可直接吃图的模型：文本里只放事实，不放中间 prompt。\n            image_hints: list[str] = []\n            for ref in image_refs:\n                img_type = self._classify_image_type(ref)\n                image_hints.append(f"[附带的{img_type}]")\n\n            annotated_text = text.strip() or "用户发送了图片。"\n            if image_hints:\n                annotated_text = annotated_text + "\\n\\n图片附件：" + "；".join(image_hints)\n\n            content: list[dict[str, Any]] = [{"type": "text", "text": annotated_text}]\n            for ref in image_refs:\n                image_part = self._image_ref_to_content_part(ref)\n                if image_part is not None:\n                    content.append(image_part)\n\n            if len(content) > 1:\n                return content\n\n        return text\n'
NEW_SANITIZER = '\n    def _sanitize_reply_before_send(self, reply: str) -> str:\n        """发送前兜底拦截：防止把系统提示词、识图中间提示词发到 QQ。"""\n        text = str(reply or "").strip()\n        if not text:\n            return ""\n\n        custom_prompt = str(getattr(self, "custom_prompt", "") or "").strip()\n\n        # 自定义人设整段泄漏\n        if custom_prompt and len(custom_prompt) >= 20 and custom_prompt[:20] in text:\n            return "喵？刚才脑袋打结了，本猫重新组织一下语言。"\n\n        prompt_keywords = [\n            "请识别这张 QQ 聊天图片",\n            "如果是表情包/梗图",\n            "如果是截图，请提取关键文字",\n            "如果是普通图片，请描述主体",\n            "用中文回答，直接描述图片内容，不要客套",\n            "请基于上面的图片内容",\n            "请自然说明你暂时没看清图片",\n            "〖图片内容解析",\n            "〖图片提示〗",\n            "来自 Qwen-VL",\n            "用户配文：",\n            "系统提示",\n            "system prompt",\n            "### 人设",\n            "### 回复风格",\n            "### 当前上下文",\n            "不要输出 Markdown",\n            "不要逐条回复",\n            "你的任务不是逐条回复",\n            "你现在的人设",\n        ]\n\n        # 如果泄漏文本里同时带着图片描述，尽量提取图片描述；否则直接阻断\n        if any(key in text for key in prompt_keywords):\n            extracted: list[str] = []\n            for raw_line in text.splitlines():\n                line = raw_line.strip().lstrip("-•* ").strip()\n                if not line:\n                    continue\n\n                # 跳过所有提示词行\n                if any(key in line for key in prompt_keywords):\n                    continue\n\n                if "张图片：" in line:\n                    desc = line.split("张图片：", 1)[-1].strip()\n                    if desc and not any(key in desc for key in prompt_keywords):\n                        extracted.append(desc)\n                elif line.startswith("图片内容："):\n                    desc = line.split("：", 1)[-1].strip()\n                    if desc and not any(key in desc for key in prompt_keywords):\n                        extracted.append(desc)\n                elif len(line) >= 6 and "识别失败" not in line:\n                    # 兜底保留像“第1张图片：...”后续被拆开的正常描述行\n                    extracted.append(line)\n\n            if extracted:\n                desc = "；".join(extracted)\n                desc = re.sub(r"\\s+", " ", desc).strip()\n                desc = desc[:180].rstrip()\n                if desc:\n                    return f"我看了下，{desc}"\n\n            return "这图我看到了，但刚才回复生成有点乱，猫猫重新看一下喵。"\n\n        for prefix in ("回复：", "回复:", "答：", "答:"):\n            if text.startswith(prefix):\n                text = text[len(prefix):].strip()\n\n        return text\n'


def find_method_range(src: str, method_name: str) -> tuple[int, int] | None:
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == method_name:
            if node.end_lineno is None:
                raise RuntimeError("当前 Python AST 没有 end_lineno，无法安全替换。")
            return node.lineno, node.end_lineno
    return None


def replace_method(src: str, method_name: str, new_method: str) -> str:
    rng = find_method_range(src, method_name)
    if rng is None:
        raise RuntimeError(f"找不到方法：{method_name}")
    start, end = rng
    lines = src.splitlines()
    new_lines = lines[: start - 1] + new_method.strip("\n").splitlines() + lines[end:]
    return "\n".join(new_lines) + "\n"


def force_sanitize_at_send(src: str) -> str:
    rng = find_method_range(src, "_send_via_gateway")
    if rng is None:
        raise RuntimeError("找不到 _send_via_gateway")
    start, end = rng
    lines = src.splitlines()

    # 先删除此方法里旧的 sanitizer 插入，避免重复
    new_lines = []
    i = 0
    while i < len(lines):
        if start - 1 <= i < end:
            line = lines[i]
            if line.strip() == "reply = self._sanitize_reply_before_send(reply)":
                i += 1
                # 如果后面紧跟旧的空回复阻止块，一并删除
                if i < len(lines) and lines[i].strip() == "if not reply:":
                    i += 1
                    if i < len(lines) and "回复为空或被安全过滤" in lines[i]:
                        i += 1
                continue
        new_lines.append(lines[i])
        i += 1

    src2 = "\n".join(new_lines) + "\n"
    rng = find_method_range(src2, "_send_via_gateway")
    if rng is None:
        raise RuntimeError("找不到 _send_via_gateway（二次定位失败）")
    start, end = rng
    lines = src2.splitlines()

    insert = [
        "        reply = self._sanitize_reply_before_send(reply)",
        "        if not reply:",
        '            return ToolResult(False, "回复为空或被安全过滤，已阻止发送。")',
    ]

    insert_at = start
    for idx in range(start - 1, min(end, start + 12)):
        if lines[idx].rstrip().endswith(":"):
            insert_at = idx + 1
            break

    lines[insert_at:insert_at] = insert
    return "\n".join(lines) + "\n"


def main() -> None:
    if not TARGET.exists():
        raise SystemExit(f"找不到文件：{TARGET}")

    src = TARGET.read_text(encoding="utf-8")
    backup = TARGET.with_suffix(".py.bak_image_prompt_pipeline_fix")
    backup.write_text(src, encoding="utf-8")

    src = replace_method(src, "_build_user_content", NEW_BUILD_USER_CONTENT)
    src = replace_method(src, "_sanitize_reply_before_send", NEW_SANITIZER)
    src = force_sanitize_at_send(src)

    compile(src, str(TARGET), "exec")
    TARGET.write_text(src, encoding="utf-8")

    print("✅ 已修复：识图 prompt 不会再进入可被发送的回复文本")
    print(f"备份文件：{backup}")
    print("下一步：")
    print("  python -m py_compile .\\src\\clawmini\\tools\\qq_auto_reply.py")
    print("  python app.py")


if __name__ == "__main__":
    main()
