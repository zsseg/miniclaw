#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修复识图后把提示词/中间提示发到群里的问题。"""

from __future__ import annotations

import ast
from pathlib import Path


PROJECT_ROOT = Path.cwd()
TARGET = PROJECT_ROOT / "src" / "clawmini" / "tools" / "qq_auto_reply.py"

NEW_SANITIZER = '\n    def _sanitize_reply_before_send(self, reply: str) -> str:\n        """发送前兜底拦截：防止把系统提示词、识图中间提示、Qwen-VL 提示词发到 QQ。"""\n        text = str(reply or "").strip()\n        if not text:\n            return ""\n\n        leak_keywords = [\n            "你现在的人设",\n            "系统提示",\n            "system prompt",\n            "### 人设",\n            "### 回复风格",\n            "### 当前上下文",\n            "不要输出 Markdown",\n            "不要逐条回复",\n            "你的任务不是逐条回复",\n            "可爱小猫娘",\n            "请识别这张 QQ 聊天图片",\n            "如果是表情包/梗图",\n            "如果是截图，请提取关键文字",\n            "如果是普通图片，请描述主体",\n            "用中文回答，直接描述图片内容，不要客套",\n            "〖图片内容解析",\n            "来自 Qwen-VL",\n            "〖图片提示〗",\n            "请基于上面的图片内容",\n            "请自然说明你暂时没看清图片",\n            "用户同时也发送了以下内容",\n            "用户配文：",\n        ]\n\n        custom_prompt = str(getattr(self, "custom_prompt", "") or "").strip()\n\n        if custom_prompt and len(custom_prompt) >= 20 and custom_prompt[:20] in text:\n            return "喵？刚才脑袋打结了，本猫重新组织一下语言。"\n\n        image_markers = ("〖图片内容解析", "来自 Qwen-VL", "请基于上面的图片内容", "请识别这张 QQ 聊天图片")\n        if any(marker in text for marker in image_markers):\n            extracted: list[str] = []\n            for raw_line in text.splitlines():\n                line = raw_line.strip().lstrip("-•* ").strip()\n                if not line:\n                    continue\n\n                if "张图片：" in line:\n                    desc = line.split("张图片：", 1)[-1].strip()\n                    if desc:\n                        extracted.append(desc)\n                elif line.startswith("图片内容："):\n                    desc = line.split("：", 1)[-1].strip()\n                    if desc:\n                        extracted.append(desc)\n\n            if extracted:\n                desc = "；".join(extracted)\n                desc = desc.replace("请基于上面的图片内容，用自然 QQ 聊天语气回复。", "").strip()\n                desc = desc[:160].rstrip()\n                if desc:\n                    return f"我看了下，{desc}"\n\n            return "这图我看到了，但刚才回复生成有点乱，猫猫重新看一下喵。"\n\n        hit_count = sum(1 for key in leak_keywords if key and key in text)\n        if hit_count >= 1:\n            return "喵？刚才脑袋打结了，本猫重新组织一下语言。"\n\n        for prefix in ("回复：", "回复:", "答：", "答:"):\n            if text.startswith(prefix):\n                text = text[len(prefix):].strip()\n\n        return text\n'


def find_method_range(src: str, method_name: str) -> tuple[int, int] | None:
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == method_name:
            if node.end_lineno is None:
                raise RuntimeError("当前 Python 版本 AST 没有 end_lineno，无法安全替换。")
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


def insert_sanitize_call_in_send(src: str) -> str:
    rng = find_method_range(src, "_send_via_gateway")
    if rng is None:
        raise RuntimeError("找不到 _send_via_gateway")
    start, end = rng
    lines = src.splitlines()

    method_text = "\n".join(lines[start - 1:end])
    if "self._sanitize_reply_before_send(reply)" in method_text:
        return src

    insert = [
        "        reply = self._sanitize_reply_before_send(reply)",
        "        if not reply:",
        '            return ToolResult(False, "回复为空或被安全过滤，已阻止发送。")',
    ]

    insert_at = start
    for idx in range(start - 1, min(end, start + 8)):
        if lines[idx].rstrip().endswith(":"):
            insert_at = idx + 1
            break

    lines[insert_at:insert_at] = insert
    return "\n".join(lines) + "\n"


def main() -> None:
    if not TARGET.exists():
        raise SystemExit(f"找不到文件：{TARGET}")

    src = TARGET.read_text(encoding="utf-8")
    backup = TARGET.with_suffix(".py.bak_no_image_prompt_leak")
    backup.write_text(src, encoding="utf-8")

    src = replace_method(src, "_sanitize_reply_before_send", NEW_SANITIZER)
    src = insert_sanitize_call_in_send(src)

    src = src.replace(
        'f"请基于上面的图片内容，用自然 QQ 聊天语气回复。"',
        'f"请只把上面的图片内容当作背景信息，最终回复时不要复述本段提示词。"',
    )
    src = src.replace(
        'f"请自然说明你暂时没看清图片，或者让对方补充说明。"',
        'f"请只根据情况自然回复，不要复述本段提示词。"',
    )

    compile(src, str(TARGET), "exec")
    TARGET.write_text(src, encoding="utf-8")

    print("✅ 已修复：识图中间提示 / 系统提示词不会再直接发到 QQ")
    print(f"备份文件：{backup}")
    print("下一步：")
    print("  python -m py_compile .\\src\\clawmini\\tools\\qq_auto_reply.py")
    print("  python app.py")


if __name__ == "__main__":
    main()
