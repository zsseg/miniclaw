#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import ast
from pathlib import Path


PROJECT_ROOT = Path.cwd()
TARGET = PROJECT_ROOT / "src" / "clawmini" / "workspace_app.py"

GUIDE_BLOCK = '\n        guide = ttk.LabelFrame(body, text="操作指引", padding=10, style="Card.TLabelframe")\n        guide.pack(fill=tk.X, pady=(8, 6))\n        guide_text = (\n            "1. 先选网关：测试选 mock，正式用 managed。\\n"\n            "2. 下载安装 NapCat：点下方「下载NapCat」按钮从官网获取。\\n"\n            "3. 安装后点「一键启动/填充」，自动识别账号和地址。\\n"\n            "4. 再点「更新配置」保存群号、延时等设置。\\n"\n            "5. 先用「模拟收到消息」测试回复效果，再切换到真实 QQ。\\n"\n            "6. 如果提示缺少 pywinauto，在终端执行：python -m pip install pywinauto"\n        )\n        ttk.Label(guide, text=guide_text, justify=tk.LEFT, style="Muted.TLabel").pack(anchor=tk.W)\n'


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


def find_existing_guide_block(lines: list[str], start: int, end: int) -> tuple[int, int] | None:
    guide_start = None
    for idx in range(start, end):
        line = lines[idx]
        if 'text="操作指引"' in line or "text='操作指引'" in line:
            for j in range(idx, max(start, idx - 8), -1):
                if "ttk.LabelFrame" in lines[j] and ("guide" in lines[j] or "help" in lines[j] or "hint" in lines[j]):
                    guide_start = j
                    break
            if guide_start is None:
                guide_start = idx
            break

    if guide_start is None:
        return None

    markers = [
        "api_box =",
        "model =",
        "cfg =",
        "groups =",
        "managed_row =",
        "actions =",
        "simulate =",
        "info =",
        "chat_box =",
        "ttk.LabelFrame(body, text=",
        "ttk.Frame(body)",
    ]
    guide_end = None
    for idx in range(guide_start + 1, end):
        if any(marker in lines[idx] for marker in markers):
            guide_end = idx
            break

    if guide_end is None:
        guide_end = guide_start + 1

    return guide_start, guide_end


def find_insert_position(lines: list[str], start: int, end: int) -> int:
    title_keywords = [
        "QQ 自动回复控制台",
        "QQ Bot Overview",
        "QQ 自动回复",
        "连接 NapCat",
    ]

    last_title_related = None
    for idx in range(start, end):
        if any(k in lines[idx] for k in title_keywords):
            last_title_related = idx

    if last_title_related is not None:
        pos = last_title_related + 1
        for idx in range(last_title_related + 1, min(end, last_title_related + 12)):
            if ".pack(" in lines[idx] or ".grid(" in lines[idx]:
                pos = idx + 1
        return pos

    markers = [
        "api_box =",
        "model =",
        "cfg =",
        "managed_row =",
        "actions =",
        "simulate =",
        "info =",
    ]
    for idx in range(start, end):
        if any(marker in lines[idx] for marker in markers):
            return idx

    raise RuntimeError("没找到合适的插入位置。请把 QQAutoReplyPanel._build_ui 顶部代码贴出来。")


def main() -> None:
    if not TARGET.exists():
        raise SystemExit(f"找不到文件：{TARGET}")

    src = TARGET.read_text(encoding="utf-8")
    backup = TARGET.with_suffix(".py.bak_restore_guide")
    backup.write_text(src, encoding="utf-8")

    start_line, end_line = find_method_range(src, "QQAutoReplyPanel", "_build_ui")
    lines = src.splitlines()
    method_start = start_line - 1
    method_end = end_line

    guide_lines = GUIDE_BLOCK.strip("\n").splitlines()
    existing = find_existing_guide_block(lines, method_start, method_end)

    if existing:
        guide_start, guide_end = existing
        new_lines = lines[:guide_start] + guide_lines + lines[guide_end:]
        action = "已更新已有操作指引"
    else:
        insert_at = find_insert_position(lines, method_start, method_end)
        new_lines = lines[:insert_at] + guide_lines + lines[insert_at:]
        action = "已加回操作指引"

    src2 = "\n".join(new_lines) + "\n"
    compile(src2, str(TARGET), "exec")
    TARGET.write_text(src2, encoding="utf-8")

    print(f"✅ {action}")
    print("恢复了第一版帮助信息：网关、NapCat、一键启动/填充、更新配置、模拟测试、pywinauto。")
    print(f"备份文件：{backup}")
    print("下一步：")
    print("  python -m py_compile .\\src\\clawmini\\workspace_app.py")
    print("  python app.py")


if __name__ == "__main__":
    main()
