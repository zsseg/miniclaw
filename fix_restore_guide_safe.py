#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import ast
import re
from pathlib import Path


PROJECT_ROOT = Path.cwd()
TARGET = PROJECT_ROOT / "src" / "clawmini" / "workspace_app.py"

BODY_GUIDE_BLOCK = '\n        # Restored operation guide\n        guide = ttk.LabelFrame(body, text="操作指引", padding=10, style="Card.TLabelframe")\n        guide.pack(fill=tk.X, pady=(8, 6))\n        guide_text = (\n            "1. 先选网关：测试选 mock，正式用 managed。\\n"\n            "2. 下载安装 NapCat：点下方「下载NapCat」按钮从官网获取。\\n"\n            "3. 安装后点「一键启动/填充」，自动识别账号和地址。\\n"\n            "4. 再点「更新配置」保存群号、延时等设置。\\n"\n            "5. 先用「模拟收到消息」测试回复效果，再切换到真实 QQ。\\n"\n            "6. 如果提示缺少 pywinauto，在终端执行：python -m pip install pywinauto"\n        )\n        ttk.Label(guide, text=guide_text, justify=tk.LEFT, style="Muted.TLabel").pack(anchor=tk.W)\n'
TITLE_BOX_GUIDE_BLOCK = '\n        # Restored operation guide\n        guide_text = (\n            "操作指引：先选网关（测试 mock / 正式 managed） → 下载 NapCat → 一键启动/填充 → 更新配置 → 模拟测试。"\n            " 如果提示缺少 pywinauto：python -m pip install pywinauto"\n        )\n        ttk.Label(\n            title_box,\n            text=guide_text,\n            justify=tk.LEFT,\n            style="Muted.TLabel",\n            wraplength=820,\n        ).grid(row=2, column=0, sticky="w", pady=(6, 0))\n'
HEADER_GUIDE_BLOCK = '\n        # Restored operation guide\n        guide_text = (\n            "操作指引：先选网关（测试 mock / 正式 managed） → 下载 NapCat → 一键启动/填充 → 更新配置 → 模拟测试。"\n            " 如果提示缺少 pywinauto：python -m pip install pywinauto"\n        )\n        ttk.Label(\n            header,\n            text=guide_text,\n            justify=tk.LEFT,\n            style="Muted.TLabel",\n            wraplength=820,\n        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(6, 0))\n'


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


def remove_existing_guides(lines: list[str], method_start: int, method_end: int) -> tuple[list[str], int]:
    out: list[str] = []
    removed = 0
    i = 0

    while i < len(lines):
        in_method = method_start <= i < method_end
        line = lines[i]

        starts_old_guide = (
            in_method
            and (
                ("guide = ttk.LabelFrame(" in line and "操作指引" in line)
                or "# Restored operation guide" in line
            )
        )

        if starts_old_guide:
            removed += 1
            base_indent = len(line) - len(line.lstrip())
            i += 1

            while i < len(lines):
                cur = lines[i]
                stripped = cur.strip()
                indent = len(cur) - len(cur.lstrip())

                if "ttk.Label(guide" in cur and ".pack(" in cur:
                    i += 1
                    break

                stop_markers = [
                    "cards = ",
                    "main = ",
                    "api_box = ",
                    "model = ",
                    "cfg = ",
                    "managed_row = ",
                    "actions = ",
                    "info = ",
                    "chat_box = ",
                    "log_card = ",
                    "status_card = ",
                ]
                if stripped and indent <= base_indent and any(stripped.startswith(marker) for marker in stop_markers):
                    break

                if "wraplength=" in cur:
                    i += 1
                    while i < len(lines):
                        if ").grid(" in lines[i]:
                            i += 1
                            break
                        i += 1
                    break

                if stripped and indent <= base_indent and not stripped.startswith(("guide_text", "ttk.Label(", ")", '"', "#")):
                    break

                i += 1

            continue

        out.append(line)
        i += 1

    return out, removed


def find_var_assignment(lines: list[str], start: int, end: int, var_name: str) -> int | None:
    pattern = re.compile(rf"^\s*{re.escape(var_name)}\s*=\s*")
    for idx in range(start, end):
        if pattern.search(lines[idx]):
            return idx
    return None


def find_after_pack_or_grid(lines: list[str], var_line: int, end: int, var_name: str) -> int:
    insert_at = var_line + 1
    for idx in range(var_line + 1, min(end, var_line + 18)):
        stripped = lines[idx].strip()
        if stripped.startswith(f"{var_name}.pack(") or stripped.startswith(f"{var_name}.grid("):
            insert_at = idx + 1
            break
    return insert_at


def find_after_title_labels(lines: list[str], title_box_line: int, end: int) -> int:
    insert_at = title_box_line + 1
    for idx in range(title_box_line + 1, min(end, title_box_line + 40)):
        if "title_box" in lines[idx] and ".grid(" in lines[idx]:
            insert_at = idx + 1
    return insert_at


def main() -> None:
    if not TARGET.exists():
        raise SystemExit(f"找不到文件：{TARGET}")

    src = TARGET.read_text(encoding="utf-8")
    backup = TARGET.with_suffix(".py.bak_restore_guide_safe")
    backup.write_text(src, encoding="utf-8")

    start_line, end_line = find_method_range(src, "QQAutoReplyPanel", "_build_ui")
    lines = src.splitlines()
    method_start = start_line - 1
    method_end = end_line

    lines, removed = remove_existing_guides(lines, method_start, method_end)

    tmp_src = "\n".join(lines) + "\n"
    start_line, end_line = find_method_range(tmp_src, "QQAutoReplyPanel", "_build_ui")
    method_start = start_line - 1
    method_end = end_line

    body_line = find_var_assignment(lines, method_start, method_end, "body")
    title_box_line = find_var_assignment(lines, method_start, method_end, "title_box")
    header_line = find_var_assignment(lines, method_start, method_end, "header")

    if body_line is not None:
        insert_at = find_after_pack_or_grid(lines, body_line, method_end, "body")
        block = BODY_GUIDE_BLOCK
        mode = "body"
    elif title_box_line is not None:
        insert_at = find_after_title_labels(lines, title_box_line, method_end)
        block = TITLE_BOX_GUIDE_BLOCK
        mode = "title_box"
    elif header_line is not None:
        insert_at = find_after_pack_or_grid(lines, header_line, method_end, "header")
        block = HEADER_GUIDE_BLOCK
        mode = "header"
    else:
        raise RuntimeError(
            "没找到 body/title_box/header。请上传 src\\clawmini\\workspace_app.py，不是 qq_auto_reply.py。"
        )

    guide_lines = block.strip("\n").splitlines()
    lines[insert_at:insert_at] = guide_lines

    src2 = "\n".join(lines) + "\n"
    compile(src2, str(TARGET), "exec")
    TARGET.write_text(src2, encoding="utf-8")

    print("✅ 已安全恢复操作指引")
    print(f"删除旧/错误操作指引块：{removed} 个")
    print(f"插入位置：{mode}")
    print(f"备份文件：{backup}")
    print("下一步：")
    print("  python -m py_compile .\\src\\clawmini\\workspace_app.py")
    print("  python app.py")


if __name__ == "__main__":
    main()
