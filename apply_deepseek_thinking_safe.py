#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""安全启用 DeepSeek Thinking。

这个脚本修复上一个补丁的问题：
- 不会再盲目在所有 json.dumps(payload...) 前插入代码；
- 会用 AST 找到“包含 json.dumps(payload) 的完整语句”，插到语句前面，避免插进 Request(...) 参数列表导致 SyntaxError；
- 只 patch 主回复 DeepSeek 请求，不 patch Qwen-VL / NapCat get_msg。

使用：
    python .\apply_deepseek_thinking_safe.py
"""

from __future__ import annotations

import ast
import shutil
from pathlib import Path


PROJECT_ROOT = Path.cwd()
TARGET = PROJECT_ROOT / "src" / "clawmini" / "tools" / "qq_auto_reply.py"
MARKER = "# DeepSeek thinking safe patch"


PATCH_BLOCK = [
    f"{MARKER}",
    'if str(getattr(self, "reply_api_provider", "") or "").strip().lower() == "deepseek":',
    '    payload["thinking"] = {"type": "enabled"}',
    '    payload["reasoning_effort"] = "high"',
    '    for _deepseek_bad_key in ("temperature", "top_p", "presence_penalty", "frequency_penalty", "enable_search", "search", "web_search"):',
    '        payload.pop(_deepseek_bad_key, None)',
    '    try:',
    '        _max_tokens = int(payload.get("max_tokens", 0) or 0)',
    '    except Exception:',
    '        _max_tokens = 0',
    '    if _max_tokens < 500:',
    '        payload["max_tokens"] = 500',
    '    for _msg in payload.get("messages", []):',
    '        if isinstance(_msg, dict) and isinstance(_msg.get("content"), list):',
    '            _parts = []',
    '            for _part in _msg.get("content", []):',
    '                if isinstance(_part, dict) and _part.get("type") == "text":',
    '                    _parts.append(str(_part.get("text", "") or ""))',
    '                elif isinstance(_part, dict) and str(_part.get("type", "")).lower() in {"image_url", "input_image"}:',
    '                    _parts.append("[图片]")',
    '            _msg["content"] = "\\n".join(_parts).strip() or "[图片]"',
]


def try_compile_text(src: str, filename: Path) -> tuple[bool, str]:
    try:
        compile(src, str(filename), "exec")
        return True, ""
    except SyntaxError as exc:
        return False, f"{exc.msg} at line {exc.lineno}"
    except Exception as exc:
        return False, repr(exc)


def restore_if_broken() -> None:
    src = TARGET.read_text(encoding="utf-8")
    ok, err = try_compile_text(src, TARGET)
    if ok:
        return

    print(f"当前 qq_auto_reply.py 语法有问题：{err}")
    candidates = [
        TARGET.with_suffix(".py.bak_thinking_payload_final"),
        TARGET.with_suffix(".py.bak_deepseek_thinking_enabled"),
        TARGET.with_suffix(".py.bak_prompt_leak_final"),
        TARGET.with_suffix(".py.bak_image_prompt_pipeline_fix"),
        TARGET.with_suffix(".py.bak_no_image_prompt_leak"),
    ]

    for bak in candidates:
        if not bak.exists():
            continue
        bak_src = bak.read_text(encoding="utf-8")
        ok, bak_err = try_compile_text(bak_src, TARGET)
        if ok:
            shutil.copy2(bak, TARGET)
            print(f"已从可用备份恢复：{bak}")
            return
        print(f"跳过不可用备份：{bak} | {bak_err}")

    raise SystemExit("没有找到可编译的备份，请手动恢复 qq_auto_reply.py 后再运行。")


def set_parents(tree: ast.AST) -> None:
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            setattr(child, "_parent", parent)


def is_json_dumps_payload(call: ast.AST) -> bool:
    if not isinstance(call, ast.Call):
        return False

    func = call.func
    is_json_dumps = (
        isinstance(func, ast.Attribute)
        and func.attr == "dumps"
        and isinstance(func.value, ast.Name)
        and func.value.id == "json"
    )
    if not is_json_dumps:
        return False

    if not call.args:
        return False

    first = call.args[0]
    return isinstance(first, ast.Name) and first.id == "payload"


def containing_stmt(node: ast.AST) -> ast.stmt | None:
    cur = node
    while True:
        parent = getattr(cur, "_parent", None)
        if parent is None:
            return None
        if isinstance(parent, ast.stmt):
            return parent
        cur = parent


def method_text(lines: list[str], node: ast.FunctionDef) -> str:
    if node.end_lineno is None:
        return ""
    return "\n".join(lines[node.lineno - 1: node.end_lineno])


def is_main_reply_method(text: str, name: str) -> bool:
    lowered = text.lower()

    if name in {"_describe_images_with_qwen_vl", "_fetch_replied_message_context"}:
        return False

    if "json.dumps(payload" not in text:
        return False

    # 排除 Qwen-VL 与 NapCat get_msg
    banned = [
        "DASHSCOPE_API_KEY",
        "QWEN_VL_MODEL",
        "qwen-vl-plus",
        "dashscope.aliyuncs.com",
        'endpoint = base_url + "/get_msg"',
        '"message_id": reply_message_id',
        "managed_access_token",
    ]
    if any(item in text for item in banned):
        return False

    # 主回复方法通常会出现这些字段
    required_any = [
        "reply_api_provider",
        "reply_api_key",
        "reply_api_base_url",
        "last_reply_api_error",
        "last_reply_api_endpoint",
        "DeepSeek",
        "deepseek",
    ]
    return any(item in text for item in required_any)


def patch_source(src: str) -> str:
    tree = ast.parse(src)
    set_parents(tree)

    lines = src.splitlines()
    insert_lines: set[int] = set()

    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or node.end_lineno is None:
            continue

        text = method_text(lines, node)
        if not is_main_reply_method(text, node.name):
            continue

        if MARKER in text:
            print(f"已存在补丁，跳过方法：{node.name}")
            continue

        for sub in ast.walk(node):
            if not is_json_dumps_payload(sub):
                continue

            stmt = containing_stmt(sub)
            if stmt is None:
                continue

            # 插到完整语句前，而不是插进 Request(...) 参数中
            insert_lines.add(stmt.lineno)

        if insert_lines:
            print(f"将 patch 方法：{node.name}")

    if not insert_lines:
        raise SystemExit(
            "没找到主回复 DeepSeek 请求位置。请把 qq_auto_reply.py 中包含 reply_api_provider 和 json.dumps(payload) 的函数贴出来。"
        )

    # 从后往前插，不影响行号
    new_lines = list(lines)
    for line_no in sorted(insert_lines, reverse=True):
        base_line = new_lines[line_no - 1]
        indent = base_line[: len(base_line) - len(base_line.lstrip())]
        block = [indent + line for line in PATCH_BLOCK]
        new_lines[line_no - 1: line_no - 1] = block

    return "\n".join(new_lines) + "\n"


def main() -> None:
    if not TARGET.exists():
        raise SystemExit(f"找不到文件：{TARGET}")

    restore_if_broken()

    src = TARGET.read_text(encoding="utf-8")
    backup = TARGET.with_suffix(".py.bak_deepseek_thinking_safe")
    backup.write_text(src, encoding="utf-8")

    patched = patch_source(src)
    ok, err = try_compile_text(patched, TARGET)
    if not ok:
        raise SystemExit(f"补丁后的代码仍然有语法错误，未写入：{err}")

    TARGET.write_text(patched, encoding="utf-8")

    print("✅ 已安全启用 DeepSeek Thinking")
    print("已设置：thinking={type: enabled}, reasoning_effort=high")
    print("已避免：Qwen-VL / NapCat get_msg 被误 patch")
    print(f"备份文件：{backup}")
    print("下一步：")
    print("  python -m py_compile .\\src\\clawmini\\tools\\qq_auto_reply.py")
    print("  python app.py")


if __name__ == "__main__":
    main()
