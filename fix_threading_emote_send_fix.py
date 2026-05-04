#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import ast
import re
from pathlib import Path

PROJECT_ROOT = Path.cwd()
TARGET = PROJECT_ROOT / "src" / "clawmini" / "tools" / "qq_auto_reply.py"

SEND_EMOTE_METHOD = '\n    def _send_emote_item_to_group(self, chat_id: str, item: dict[str, Any]) -> ToolResult:\n        """发送收藏或当前消息里的表情项。\n\n        image 优先尝试 CQ file 字段，失败再回退 url。\n        """\n        if not isinstance(item, dict):\n            return ToolResult(False, "无效表情项。")\n\n        emote_type = str(item.get("type", "") or "")\n        data = item.get("data", {})\n        if not isinstance(data, dict):\n            data = {}\n\n        if emote_type == "face":\n            face_id = data.get("id")\n            if face_id in (None, ""):\n                return ToolResult(False, "表情缺少 id。")\n            return self._send_group_segments_via_napcat(\n                chat_id,\n                [{"type": "face", "data": {"id": int(face_id) if str(face_id).isdigit() else face_id}}],\n            )\n\n        if emote_type == "image":\n            candidates: list[str] = []\n            for value in (\n                item.get("file"),\n                data.get("file"),\n                item.get("url"),\n                data.get("url"),\n            ):\n                value = str(value or "").strip()\n                if value and value not in candidates:\n                    candidates.append(value)\n\n            if not candidates:\n                return ToolResult(False, "图片表情缺少 file/url。")\n\n            last_result: ToolResult | None = None\n            for file_value in candidates:\n                result = self._send_group_segments_via_napcat(\n                    chat_id,\n                    [{"type": "image", "data": {"file": file_value}}],\n                )\n                if result.success:\n                    return result\n                last_result = result\n\n            return last_result or ToolResult(False, "图片表情发送失败。")\n\n        return ToolResult(False, f"未知表情类型：{emote_type}")\n'


def method_range(src: str, method_name: str) -> tuple[int, int] | None:
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == method_name:
            if node.end_lineno is None:
                raise RuntimeError("AST 没有 end_lineno")
            return node.lineno, node.end_lineno
    return None


def replace_method(src: str, method_name: str, method_text: str) -> str:
    rng = method_range(src, method_name)
    if rng is None:
        raise RuntimeError(f"找不到方法：{method_name}")
    start, end = rng
    lines = src.splitlines()
    new_lines = lines[: start - 1] + method_text.strip("\n").splitlines() + lines[end:]
    return "\n".join(new_lines) + "\n"


def add_threading_import(src: str) -> str:
    if re.search(r"^\s*import\s+threading\s*$", src, flags=re.M):
        return src

    lines = src.splitlines()
    insert_at = 0
    for i, line in enumerate(lines):
        if line.startswith("import ") or line.startswith("from "):
            insert_at = i + 1
        elif insert_at and line.strip() and not line.startswith((" ", "\t")):
            break

    lines.insert(insert_at, "import threading")
    return "\n".join(lines) + "\n"


def patch_prefer_file_over_url(src: str) -> str:
    return src.replace("send_file = url_value or file_value", "send_file = file_value or url_value")


def patch_reply_label(src: str) -> str:
    src = re.sub(
        r'reply_label\s*=\s*f"\[已跟发表情\][^\n]*"',
        'reply_label = "[已发送一个表情]"',
        src,
    )
    src = re.sub(
        r'reply_label\s*=\s*f"\[已复读表情包\][^\n]*"',
        'reply_label = "[已发送一个表情]"',
        src,
    )
    return src


def main() -> None:
    if not TARGET.exists():
        raise SystemExit(f"找不到文件：{TARGET}")

    src = TARGET.read_text(encoding="utf-8")
    backup = TARGET.with_suffix(".py.bak_threading_emote_send_fix")
    backup.write_text(src, encoding="utf-8")

    src = add_threading_import(src)
    src = patch_prefer_file_over_url(src)

    if method_range(src, "_send_emote_item_to_group") is not None:
        src = replace_method(src, "_send_emote_item_to_group", SEND_EMOTE_METHOD)
    else:
        print("⚠️ 没找到 _send_emote_item_to_group，跳过表情发送优化。")

    src = patch_reply_label(src)

    compile(src, str(TARGET), "exec")
    TARGET.write_text(src, encoding="utf-8")

    print("✅ 已修复 threading 缺失 + 表情发送速度/日志占位")
    print("1. 已补 import threading，QQVision 不会再因为 name 'threading' is not defined 失败。")
    print("2. 图片表情发送优先用 CQ file 字段，失败再回退 URL，通常会比直接 URL 快。")
    print("3. UI 日志里的表情发送占位改成 [已发送一个表情]，避免误以为群里发了文字。")
    print(f"备份文件：{backup}")
    print("下一步：")
    print("  python -m py_compile .\\src\\clawmini\\tools\\qq_auto_reply.py")
    print("  python app.py")


if __name__ == "__main__":
    main()
