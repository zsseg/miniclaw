#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修复 QQ 自动回复页 Recent Status 区域。

改动：
1. 把容易被长 URL 撑乱的黑色 Recent Status 卡片，改成米白摘要卡。
2. Webhook 地址改成只读 Entry，方便复制，不会撑爆布局。
3. 自动备份 workspace_app.py。
"""

from __future__ import annotations

import ast
from pathlib import Path


PROJECT_ROOT = Path.cwd()
WORKSPACE_APP = PROJECT_ROOT / "src" / "clawmini" / "workspace_app.py"


NEW_STATUS_BLOCK = r'''
        status_card = tk.Frame(
            right,
            bg="#fff8e8",
            highlightbackground="#2a2521",
            highlightthickness=1,
        )
        status_card.grid(row=0, column=0, sticky="ew")
        status_card.grid_columnconfigure(0, weight=1)

        status_head = tk.Frame(status_card, bg="#fff8e8")
        status_head.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 4))
        status_head.grid_columnconfigure(0, weight=1)

        tk.Label(
            status_head,
            text="Recent Status",
            bg="#fff8e8",
            fg="#26211f",
            font=("Georgia", 10, "bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="ew")

        tk.Label(
            status_head,
            text="LIVE",
            bg="#285d52",
            fg="#fff8e8",
            font=("Georgia", 6, "bold"),
            padx=7,
            pady=2,
        ).grid(row=0, column=1, sticky="e")

        tk.Label(
            status_card,
            textvariable=self.qq_status_text,
            bg="#fff8e8",
            fg="#26211f",
            font=("Microsoft YaHei UI", 9),
            justify=tk.LEFT,
            anchor="w",
            wraplength=260,
        ).grid(row=1, column=0, sticky="ew", padx=12, pady=(2, 8))

        tk.Label(
            status_card,
            text="Webhook",
            bg="#fff8e8",
            fg="#756c61",
            font=("Georgia", 8, "bold"),
            anchor="w",
        ).grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 2))

        webhook_entry = ttk.Entry(
            status_card,
            textvariable=self.qq_webhook_url_var,
            state="readonly",
        )
        webhook_entry.grid(row=3, column=0, sticky="ew", padx=12, pady=(0, 10))
'''


def find_method_range(src: str, class_name: str, method_name: str) -> tuple[int, int]:
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == method_name:
                    if item.end_lineno is None:
                        raise RuntimeError("当前 Python AST 没有 end_lineno，无法安全替换。")
                    return item.lineno, item.end_lineno
    raise RuntimeError(f"找不到 {class_name}.{method_name}")


def main() -> None:
    if not WORKSPACE_APP.exists():
        raise SystemExit(f"找不到文件：{WORKSPACE_APP}")

    src = WORKSPACE_APP.read_text(encoding="utf-8")
    backup = WORKSPACE_APP.with_suffix(".py.bak_recent_status")
    backup.write_text(src, encoding="utf-8")

    start_line, end_line = find_method_range(src, "QQAutoReplyPanel", "_build_ui")
    lines = src.splitlines()

    # 只在 QQAutoReplyPanel._build_ui 范围内查找，避免误替换别的函数。
    method_start = start_line - 1
    method_end = end_line

    status_start = None
    action_start = None

    for idx in range(method_start, method_end):
        if "status_card = tk.Frame(" in lines[idx] or "status_card = tk.Frame(right" in lines[idx]:
            status_start = idx
            break

    if status_start is None:
        raise SystemExit("没找到 status_card = tk.Frame(...)，可能你的 UI 结构已变化。")

    for idx in range(status_start + 1, method_end):
        if "action_card = ttk.LabelFrame(" in lines[idx]:
            action_start = idx
            break

    if action_start is None:
        raise SystemExit("没找到 action_card = ttk.LabelFrame(...)，无法确定 Recent Status 区块结束位置。")

    new_block_lines = NEW_STATUS_BLOCK.strip("\n").splitlines()
    new_lines = lines[:status_start] + new_block_lines + lines[action_start:]
    src2 = "\n".join(new_lines) + "\n"

    compile(src2, str(WORKSPACE_APP), "exec")
    WORKSPACE_APP.write_text(src2, encoding="utf-8")

    print("✅ Recent Status 已修复")
    print(f"备份文件：{backup}")
    print("下一步：")
    print("  python -m py_compile .\\src\\clawmini\\workspace_app.py")
    print("  python app.py")


if __name__ == "__main__":
    main()
