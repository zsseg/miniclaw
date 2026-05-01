#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import ast
from pathlib import Path

PROJECT_ROOT = Path.cwd()
TARGET = PROJECT_ROOT / "src" / "clawmini" / "tools" / "qq_auto_reply.py"
MARKER = "# DeepSeek text-only payload fix"

PATCH_BLOCK = [
    MARKER,
    'if provider == "deepseek":',
    '    for _msg in payload.get("messages", []):',
    '        if not isinstance(_msg, dict):',
    '            continue',
    '        _content = _msg.get("content")',
    '        if isinstance(_content, list):',
    '            _parts = []',
    '            for _part in _content:',
    '                if not isinstance(_part, dict):',
    '                    continue',
    '                _type = str(_part.get("type", "")).lower()',
    '                if _type == "text":',
    '                    _parts.append(str(_part.get("text", "") or ""))',
    '                elif _type in {"image_url", "input_image"}:',
    '                    _parts.append("[图片]")',
    '                else:',
    '                    _parts.append(f"[{_type}]")',
    '            _msg["content"] = "\\n".join(p for p in _parts if p).strip() or "[图片]"',
    '        elif _content is None:',
    '            _msg["content"] = ""',
    '        else:',
    '            _msg["content"] = str(_content)',
    '    payload["thinking"] = {"type": "enabled"}',
    '    payload["reasoning_effort"] = "high"',
    '    for _bad_key in ("temperature", "top_p", "presence_penalty", "frequency_penalty", "enable_search", "search", "web_search"):',
    '        payload.pop(_bad_key, None)',
    '    try:',
    '        _max_tokens = int(payload.get("max_tokens", 0) or 0)',
    '    except Exception:',
    '        _max_tokens = 0',
    '    if _max_tokens < 500:',
    '        payload["max_tokens"] = 500',
]


def method_range(src: str, method_name: str) -> tuple[int, int]:
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == method_name:
            if node.end_lineno is None:
                raise RuntimeError("AST 没有 end_lineno")
            return node.lineno, node.end_lineno
    raise RuntimeError(f"找不到方法：{method_name}")


def add_urllib_error_import(src: str) -> str:
    if "import urllib.error" in src:
        return src
    if "import urllib.request" in src:
        return src.replace("import urllib.request", "import urllib.request\nimport urllib.error", 1)
    return "import urllib.error\n" + src


def strip_old_deepseek_blocks(method_lines: list[str]) -> list[str]:
    cleaned: list[str] = []
    i = 0
    while i < len(method_lines):
        line = method_lines[i]
        stripped = line.strip()
        remove = (
            stripped == MARKER
            or stripped == "# DeepSeek V4 thinking mode: enabled"
            or stripped == "# DeepSeek thinking safe patch"
            or stripped.startswith('if provider == "deepseek" and model_name.startswith("deepseek-v4")')
        )
        if remove:
            base_indent = len(line) - len(line.lstrip())
            i += 1
            while i < len(method_lines):
                nxt = method_lines[i]
                nxt_stripped = nxt.strip()
                nxt_indent = len(nxt) - len(nxt.lstrip())
                if nxt_stripped and nxt_indent <= base_indent:
                    break
                i += 1
            continue
        cleaned.append(line)
        i += 1
    return cleaned


def patch_generate_reply_via_api(src: str) -> str:
    start, end = method_range(src, "_generate_reply_via_api")
    lines = src.splitlines()
    method_lines = lines[start - 1:end]
    method_lines = strip_old_deepseek_blocks(method_lines)

    patched: list[str] = []
    inserted = False
    for line in method_lines:
        if not inserted and "json.dumps(payload" in line:
            indent = line[: len(line) - len(line.lstrip())]
            patched.extend([indent + x for x in PATCH_BLOCK])
            inserted = True
        patched.append(line)

    if not inserted:
        raise RuntimeError("_generate_reply_via_api 中没找到 json.dumps(payload...)")

    new_lines = lines[: start - 1] + patched + lines[end:]
    return "\n".join(new_lines) + "\n"


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
    backup = TARGET.with_suffix(".py.bak_deepseek_image_url_400_fix")
    backup.write_text(src, encoding="utf-8")

    src = add_urllib_error_import(src)
    src = remove_deepseek_thinking_from_qwen_vl(src)
    src = patch_generate_reply_via_api(src)

    compile(src, str(TARGET), "exec")
    TARGET.write_text(src, encoding="utf-8")

    print("✅ 已修复 DeepSeek image_url 400")
    print("DeepSeek 主请求会把 content list / image_url 强制转成纯文本。")
    print("Qwen-VL 识图请求里的 DeepSeek thinking 参数也已清理。")
    print(f"备份文件：{backup}")
    print("下一步：")
    print("  python -m py_compile .\\src\\clawmini\\tools\\qq_auto_reply.py")
    print("  python app.py")


if __name__ == "__main__":
    main()
