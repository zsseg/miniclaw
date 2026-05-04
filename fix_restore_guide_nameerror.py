#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修复“操作指引”插入到 body 定义之前导致的 NameError。

错误：
    NameError: name 'body' is not defined

原因：
    上一个 restore guide 脚本把 guide = ttk.LabelFrame(body, ...)
    插到了 QQAutoReplyPanel._build_ui() 里 body 创建之前。

本脚本会：
1. 删除当前位置错误的“操作指引”块；
2. 找到 body = ... 以及 body.pack/body.grid 之后；
3. 把“操作指引”重新插入到 body 已经存在的位置。
"""

from __future__ import annotations

import ast
import re
from pathlib import Path


PROJECT_ROOT = Path.cwd()
TARGET = PROJECT_ROOT / "src" / "clawmini" / "workspace_app.py"


GUIDE_BLOCK = """
        guide = ttk.LabelFrame(body, text="操作指引", padding=10, style="Card.TLabelframe")
        guide.pack(fill=tk.X, pady=(8, 6))
        guide_text = (
            "1. 先选网关：测试选 mock，正式用 managed。\\\\n"
            "2. 下载安装 NapCat：点下方「下载NapCat」按钮从官网获取。\\\\n"
            "3. 安装后点「一键启动/填充」，自动识别账号和地址。\\\\n"
            "4. 再点「更新配置」保存群号、延时等设置。\\\\n"
            "5. 先用「模拟收到消息」测试回复效果，再切换到真实 QQ。\\\\n"
            "6. 如果提示缺少 pywinauto，在终端执行：python -m pip install pywinauto"
        )
        ttk.Label(guide, text=guide_text, justify=tk.LEFT, style="Muted.TLabel").pack(anchor=tk.W)
"""


def find_method_range(src: str, class_name: str, method_name: str) -> tuple[int, int]:
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == method_name:
                    if item.end_lineno is None:
                        raise RuntimeError("AST 没有 end_lineno，无法安全替换。")
                    return item.lineno, item.end_lineno
    raise RuntimeError(f"找不到 {class_name}.{method_name}")


def remove_guide_blocks(lines: list[str], method_start: int, method_end: int) -> tuple[list[str], int]:
    """删除 _build_ui 里的所有 操作指引 guide block。"""
    out: list[str] = []
    removed = 0
    i = 0

    while i < len(lines):
        in_method = method_start <= i < method_end
        line = lines[i]

        if in_method and "guide = ttk.LabelFrame(body" in line and "操作指引" in line:
            removed += 1
            i += 1
            # 删除到 ttk.Label(guide, ...) 这一行结束
            while i < len(lines):
                if "ttk.Label(guide" in lines[i] and ".pack(" in lines[i]:
                    i += 1
                    break
                i += 1
            continue

        out.append(line)
        i += 1

    return out, removed


def find_insert_after_body(lines: list[str], method_start: int, method_end: int) -> int:
    body_line = None
    body_assign_patterns = [
        re.compile(r"^\s*body\s*=\s*"),
        re.compile(r"^\s*self\.body\s*=\s*"),
    ]

    for idx in range(method_start, method_end):
        if any(p.search(lines[idx]) for p in body_assign_patterns):
            body_line = idx
            break

    if body_line is None:
        raise RuntimeError("没找到 body = ...。请把 QQAutoReplyPanel._build_ui() 开头贴出来。")

    # 插在 body.pack/body.grid 后面；如果没有 pack/grid，就插在 body = ... 下一行。
    insert_at = body_line + 1
    for idx in range(body_line + 1, min(method_end, body_line + 12)):
        stripped = lines[idx].strip()
        if stripped.startswith("body.pack(") or stripped.startswith("body.grid("):
            insert_at = idx + 1
            break

    return insert_at


def main() -> None:
    if not TARGET.exists():
        raise SystemExit(f"找不到文件：{TARGET}")

    src = TARGET.read_text(encoding="utf-8")
    backup = TARGET.with_suffix(".py.bak_restore_guide_nameerror")
    backup.write_text(src, encoding="utf-8")

    start_line, end_line = find_method_range(src, "QQAutoReplyPanel", "_build_ui")
    lines = src.splitlines()

    method_start = start_line - 1
    method_end = end_line

    lines, removed = remove_guide_blocks(lines, method_start, method_end)

    # 删除后重新算范围，避免行号偏移
    tmp_src = "\n".join(lines) + "\n"
    start_line, end_line = find_method_range(tmp_src, "QQAutoReplyPanel", "_build_ui")
    method_start = start_line - 1
    method_end = end_line

    insert_at = find_insert_after_body(lines, method_start, method_end)
    guide_lines = GUIDE_BLOCK.strip("\n").splitlines()
    lines[insert_at:insert_at] = guide_lines

    src2 = "\n".join(lines) + "\n"
    compile(src2, str(TARGET), "exec")
    TARGET.write_text(src2, encoding="utf-8")

    print("✅ 已修复操作指引插入位置")
    print(f"删除错误位置的操作指引块：{removed} 个")
    print("已重新插入到 body 创建之后。")
    print(f"备份文件：{backup}")
    print("下一步：")
    print("  python -m py_compile .\\src\\clawmini\\workspace_app.py")
    print("  python app.py")


if __name__ == "__main__":
    main()
