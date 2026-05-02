#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import ast
from pathlib import Path


PROJECT_ROOT = Path.cwd()
TARGET = PROJECT_ROOT / "src" / "clawmini" / "workspace_app.py"

TITLE_BOX_GUIDE_BLOCK = '\n        # Restored operation guide\n        guide_text = (\n            "操作指引：先选网关（测试 mock / 正式 managed） → 下载 NapCat → 一键启动/填充 → 更新配置 → 模拟测试。"\n            " 缺少 pywinauto 时执行：python -m pip install pywinauto"\n        )\n        ttk.Label(\n            title_box,\n            text=guide_text,\n            justify=tk.LEFT,\n            style="Muted.TLabel",\n            wraplength=820,\n        ).grid(row=2, column=0, sticky="w", pady=(6, 0))\n'


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


def main() -> None:
    if not TARGET.exists():
        raise SystemExit(f"找不到文件：{TARGET}")

    src = TARGET.read_text(encoding="utf-8")
    backup = TARGET.with_suffix(".py.bak_fix_orphan_guide")
    backup.write_text(src, encoding="utf-8")

    start_line, end_line = find_method_range(src, "QQAutoReplyPanel", "_build_ui")
    lines = src.splitlines()
    method_start = start_line - 1
    method_end = end_line

    title_box_line = None
    action_shell_line = None

    for idx in range(method_start, method_end):
        if title_box_line is None and "title_box =" in lines[idx]:
            title_box_line = idx
        if "action_shell =" in lines[idx]:
            action_shell_line = idx
            break

    if title_box_line is None:
        raise SystemExit("没找到 title_box。请贴 QQAutoReplyPanel._build_ui() 开头。")
    if action_shell_line is None:
        raise SystemExit("没找到 action_shell。请贴 QQAutoReplyPanel._build_ui() 开头。")

    guide_markers = [
        "# Restored operation guide",
        "guide = ttk.LabelFrame",
        "guide.pack(",
        "guide_text =",
        "ttk.Label(guide",
        "操作指引",
        "先选网关",
        "pywinauto",
    ]

    guide_start = None
    for idx in range(title_box_line + 1, action_shell_line):
        if any(marker in lines[idx] for marker in guide_markers):
            guide_start = idx
            break

    guide_lines = TITLE_BOX_GUIDE_BLOCK.strip("\n").splitlines()

    if guide_start is None:
        insert_at = action_shell_line
        removed_count = 0
        new_lines = lines[:insert_at] + guide_lines + lines[insert_at:]
    else:
        removed_count = action_shell_line - guide_start
        new_lines = lines[:guide_start] + guide_lines + lines[action_shell_line:]

    src2 = "\n".join(new_lines) + "\n"
    compile(src2, str(TARGET), "exec")
    TARGET.write_text(src2, encoding="utf-8")

    print("✅ 已修复操作指引残留半截问题")
    print(f"删除 title_box 与 action_shell 之间残留行：{removed_count} 行")
    print("操作指引已重新挂到 title_box，不再依赖 body/guide 变量。")
    print(f"备份文件：{backup}")
    print("下一步：")
    print("  python -m py_compile .\\src\\clawmini\\workspace_app.py")
    print("  python app.py")


if __name__ == "__main__":
    main()
