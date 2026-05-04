#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""启用 DeepSeek Thinking 模式。

你的诊断已经确认：
- thinking={"type":"disabled"} + reasoning_effort="high" 会 400
- 要开思考，应使用 thinking={"type":"enabled"} + reasoning_effort="high" 或 "max"

本脚本会：
1. 在 DeepSeek 请求方法里，发送前强制设置：
   payload["thinking"] = {"type": "enabled"}
   payload["reasoning_effort"] = "high"
2. 删除之前可能打过的 payload.pop("thinking") / payload.pop("reasoning_effort") 防冲突代码。
3. 删除 thinking disabled 的直接赋值。
4. 移除 thinking 模式下无效的 temperature/top_p/presence_penalty/frequency_penalty，避免干扰。
5. 自动备份 qq_auto_reply.py。
"""

from __future__ import annotations

import ast
from pathlib import Path


PROJECT_ROOT = Path.cwd()
TARGET = PROJECT_ROOT / "src" / "clawmini" / "tools" / "qq_auto_reply.py"

PATCH_MARKER = "# DeepSeek V4 thinking mode: enabled"


def method_ranges(src: str) -> list[tuple[str, int, int, str]]:
    tree = ast.parse(src)
    lines = src.splitlines()
    ranges: list[tuple[str, int, int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.end_lineno is not None:
            text = "\n".join(lines[node.lineno - 1: node.end_lineno])
            ranges.append((node.name, node.lineno, node.end_lineno, text))
    return ranges


def find_deepseek_methods(src: str) -> list[tuple[str, int, int, str]]:
    result = []
    for name, start, end, text in method_ranges(src):
        lower = text.lower()
        if "json.dumps(payload" not in text:
            continue
        if "deepseek" in lower or "deepseek 请求失败" in text:
            result.append((name, start, end, text))
    return result


def remove_old_conflict_blocks(lines: list[str], start: int, end: int) -> list[str]:
    """在目标方法范围内删掉旧的 disabled / pop thinking 逻辑。"""
    out: list[str] = []
    i = 0
    while i < len(lines):
        in_range = (start - 1) <= i < end
        stripped = lines[i].strip()

        if in_range:
            # 删除之前“禁用 thinking”或“移除 thinking”的补丁块
            if stripped == "# DeepSeek V4 safety: remove conflicting thinking/reasoning fields":
                i += 1
                continue

            if stripped in {
                'payload.pop("thinking", None)',
                "payload.pop('thinking', None)",
                'payload.pop("reasoning_effort", None)',
                "payload.pop('reasoning_effort', None)",
            }:
                i += 1
                continue

            # 删除明显的 disabled 赋值，后面会统一设置 enabled
            if 'payload["thinking"]' in stripped and '"disabled"' in stripped:
                i += 1
                continue
            if "payload['thinking']" in stripped and "'disabled'" in stripped:
                i += 1
                continue

            # 删除 dict literal 里的 disabled 行
            if stripped.startswith(('"thinking"', "'thinking'")) and "disabled" in stripped:
                i += 1
                continue

        out.append(lines[i])
        i += 1

    return out


def patch_deepseek_method(src: str, start: int, end: int) -> str:
    lines = src.splitlines()
    lines = remove_old_conflict_blocks(lines, start, end)

    # 删除后重新计算：用文本范围大致定位同一个方法
    src2 = "\n".join(lines) + "\n"
    ranges = find_deepseek_methods(src2)
    if not ranges:
        raise RuntimeError("删除旧块后找不到 DeepSeek 请求方法。")

    # 选包含原 start 附近的方法，找不到就选第一个
    chosen = None
    for name, s, e, text in ranges:
        if abs(s - start) < 80:
            chosen = (name, s, e, text)
            break
    if chosen is None:
        chosen = ranges[0]

    name, start, end, text = chosen
    lines = src2.splitlines()

    # 如果已经有 enabled patch，不重复插
    method_text = "\n".join(lines[start - 1:end])
    if PATCH_MARKER in method_text:
        return src2

    new_lines: list[str] = []
    for idx, line in enumerate(lines):
        # 只在目标方法内，且在 json.dumps(payload...) 前插入
        if (start - 1) <= idx < end and "json.dumps(payload" in line:
            indent = line[: len(line) - len(line.lstrip())]
            new_lines.extend([
                f"{indent}{PATCH_MARKER}",
                f"{indent}if isinstance(payload, dict):",
                f"{indent}    payload[\"thinking\"] = {{\"type\": \"enabled\"}}",
                f"{indent}    payload[\"reasoning_effort\"] = \"high\"",
                f"{indent}    payload.pop(\"temperature\", None)",
                f"{indent}    payload.pop(\"top_p\", None)",
                f"{indent}    payload.pop(\"presence_penalty\", None)",
                f"{indent}    payload.pop(\"frequency_penalty\", None)",
            ])
        new_lines.append(line)

    return "\n".join(new_lines) + "\n"


def main() -> None:
    if not TARGET.exists():
        raise SystemExit(f"找不到文件：{TARGET}")

    src = TARGET.read_text(encoding="utf-8")
    backup = TARGET.with_suffix(".py.bak_deepseek_thinking_enabled")
    backup.write_text(src, encoding="utf-8")

    methods = find_deepseek_methods(src)
    if not methods:
        raise SystemExit("没找到 DeepSeek 请求方法。请把 qq_auto_reply.py 里包含 DeepSeek 请求失败 的函数贴出来。")

    # 优先选名字或文本里最像 DeepSeek 回复 API 的方法
    chosen = None
    for item in methods:
        name, start, end, text = item
        lower = (name + "\n" + text).lower()
        if "deepseek" in lower and "chat/completions" in lower:
            chosen = item
            break
    if chosen is None:
        chosen = methods[0]

    name, start, end, text = chosen
    patched = patch_deepseek_method(src, start, end)

    compile(patched, str(TARGET), "exec")
    TARGET.write_text(patched, encoding="utf-8")

    print("✅ 已启用 DeepSeek thinking 模式")
    print(f"目标方法：{name}，大约行号：{start}-{end}")
    print("已设置：thinking={type: enabled}, reasoning_effort=high")
    print("已移除：thinking disabled、reasoning_effort 冲突 pop、thinking 模式下无效采样参数")
    print(f"备份文件：{backup}")
    print("下一步：")
    print("  python -m py_compile .\\src\\clawmini\\tools\\qq_auto_reply.py")
    print("  python app.py")


if __name__ == "__main__":
    main()
