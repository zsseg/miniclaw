#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import ast
from pathlib import Path


PROJECT_ROOT = Path.cwd()
TARGET = PROJECT_ROOT / "src" / "clawmini" / "tools" / "qq_auto_reply.py"

HELPER_METHOD = '\n    def _prepare_deepseek_payload(self, payload: dict[str, Any], endpoint: str = "") -> dict[str, Any]:\n        # 发送 DeepSeek 前统一整理 payload，避免 400。\n        # Qwen-VL 识图也走 /chat/completions，但 endpoint 是 DashScope，不能加 DeepSeek thinking。\n        if not isinstance(payload, dict):\n            return payload\n\n        endpoint_text = str(endpoint or "").lower()\n        provider = str(getattr(self, "reply_api_provider", "") or "").strip().lower()\n\n        is_qwen_vl_endpoint = (\n            "dashscope" in endpoint_text\n            or "aliyuncs" in endpoint_text\n            or "qwen" in endpoint_text\n        )\n\n        is_deepseek_endpoint = (\n            "deepseek" in endpoint_text\n            or (provider == "deepseek" and not is_qwen_vl_endpoint)\n        )\n\n        if not is_deepseek_endpoint:\n            return payload\n\n        fixed = dict(payload)\n\n        messages = fixed.get("messages")\n        if isinstance(messages, list):\n            new_messages: list[dict[str, Any]] = []\n            for msg in messages:\n                if not isinstance(msg, dict):\n                    continue\n\n                new_msg = dict(msg)\n                content = new_msg.get("content")\n\n                if isinstance(content, list):\n                    parts: list[str] = []\n                    for part in content:\n                        if not isinstance(part, dict):\n                            continue\n                        p_type = str(part.get("type", "")).lower()\n                        if p_type == "text":\n                            parts.append(str(part.get("text", "") or ""))\n                        elif p_type in {"image_url", "input_image"}:\n                            parts.append("[图片]")\n                        else:\n                            parts.append(f"[{p_type}]")\n                    new_msg["content"] = "\\n".join(p for p in parts if p).strip() or "[图片]"\n                elif content is None:\n                    new_msg["content"] = ""\n                else:\n                    new_msg["content"] = str(content)\n\n                new_messages.append(new_msg)\n\n            fixed["messages"] = new_messages\n\n        fixed["thinking"] = {"type": "enabled"}\n        fixed["reasoning_effort"] = "high"\n\n        for key in (\n            "temperature",\n            "top_p",\n            "presence_penalty",\n            "frequency_penalty",\n            "enable_search",\n            "search",\n            "web_search",\n        ):\n            fixed.pop(key, None)\n\n        try:\n            max_tokens = int(fixed.get("max_tokens", 0) or 0)\n        except Exception:\n            max_tokens = 0\n        if max_tokens < 300:\n            fixed["max_tokens"] = 500\n\n        return fixed\n'
DEBUG_HELPER = '\ndef _format_http_error_body_for_debug(exc: BaseException) -> str:\n    try:\n        if isinstance(exc, urllib.error.HTTPError):\n            body = exc.read().decode("utf-8", errors="replace")\n            return f"HTTP {exc.code} {exc.reason} | {body[:2000]}"\n    except Exception:\n        pass\n    return str(exc)\n'


def find_class_range(src: str, class_name: str) -> tuple[int, int]:
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            if node.end_lineno is None:
                raise RuntimeError("AST 没有 end_lineno")
            return node.lineno, node.end_lineno
    raise RuntimeError(f"找不到 class {class_name}")


def insert_helper(src: str) -> str:
    if "def _prepare_deepseek_payload(" in src:
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "_prepare_deepseek_payload":
                if node.end_lineno is None:
                    raise RuntimeError("AST 没有 end_lineno")
                lines = src.splitlines()
                new_lines = lines[: node.lineno - 1] + HELPER_METHOD.strip("\n").splitlines() + lines[node.end_lineno:]
                return "\n".join(new_lines) + "\n"

    lines = src.splitlines()
    tree = ast.parse(src)
    insert_line = None

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_describe_images_with_qwen_vl":
            insert_line = node.lineno - 1
            break

    if insert_line is None:
        _class_start, class_end = find_class_range(src, "QQAutoReplyTool")
        insert_line = class_end - 1

    new_lines = lines[:insert_line] + HELPER_METHOD.strip("\n").splitlines() + [""] + lines[insert_line:]
    return "\n".join(new_lines) + "\n"


def patch_json_dumps(src: str) -> str:
    lines = src.splitlines()
    out: list[str] = []

    for line in lines:
        if "json.dumps(payload" in line:
            indent = line[: len(line) - len(line.lstrip())]
            previous = "\n".join(out[-6:])
            if "_prepare_deepseek_payload(payload" not in previous:
                out.append(f"{indent}payload = self._prepare_deepseek_payload(payload, endpoint)")
        out.append(line)

    return "\n".join(out) + "\n"


def add_urllib_error_import(src: str) -> str:
    if "import urllib.error" in src:
        return src
    if "import urllib.request" in src:
        return src.replace("import urllib.request", "import urllib.request\nimport urllib.error", 1)
    return "import urllib.error\n" + src


def patch_debug_helper(src: str) -> str:
    if "def _format_http_error_body_for_debug(" in src:
        return src

    marker = "NAPCAT_RELEASE_URL"
    if marker in src:
        return src.replace(marker, DEBUG_HELPER + "\n" + marker, 1)
    return DEBUG_HELPER + "\n" + src


def patch_exception_messages(src: str) -> str:
    src = src.replace('f"DeepSeek 请求失败：{exc}"', 'f"DeepSeek 请求失败：{_format_http_error_body_for_debug(exc)}"')
    src = src.replace("f'DeepSeek 请求失败：{exc}'", "f'DeepSeek 请求失败：{_format_http_error_body_for_debug(exc)}'")
    src = src.replace('f"DeepSeek 请求失败: {exc}"', 'f"DeepSeek 请求失败: {_format_http_error_body_for_debug(exc)}"')
    src = src.replace("f'DeepSeek 请求失败: {exc}'", "f'DeepSeek 请求失败: {_format_http_error_body_for_debug(exc)}'")
    return src


def main() -> None:
    if not TARGET.exists():
        raise SystemExit(f"找不到文件：{TARGET}")

    src = TARGET.read_text(encoding="utf-8")
    backup = TARGET.with_suffix(".py.bak_thinking_payload_final")
    backup.write_text(src, encoding="utf-8")

    src = add_urllib_error_import(src)
    src = patch_debug_helper(src)
    src = insert_helper(src)
    src = patch_json_dumps(src)
    src = patch_exception_messages(src)

    compile(src, str(TARGET), "exec")
    TARGET.write_text(src, encoding="utf-8")

    print("✅ 已完成 DeepSeek Thinking payload 最终修复")
    print("已做：只给 DeepSeek 主请求加 thinking enabled；Qwen-VL 不加；list content 转文本；移除冲突参数。")
    print(f"备份文件：{backup}")
    print("下一步：")
    print("  python -m py_compile .\\src\\clawmini\\tools\\qq_auto_reply.py")
    print("  python app.py")


if __name__ == "__main__":
    main()
