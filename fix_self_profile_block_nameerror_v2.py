#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修复 self_profile_block 未定义导致 bot 不说话。

修复内容：
1. 如果缺 _build_wick_self_profile_text，就补一个兜底方法。
2. 在 _generate_reply_via_api() 中首次使用 self_profile_block 前，补上定义。
3. 修复上一个修复脚本自身的 f-string 生成错误。
"""

from __future__ import annotations

import ast
from pathlib import Path


PROJECT_ROOT = Path.cwd()
TARGET = PROJECT_ROOT / "src" / "clawmini" / "tools" / "qq_auto_reply.py"

FALLBACK_PROFILE_METHOD = '\n    def _build_wick_self_profile_text(self, context_info: dict[str, Any] | None = None) -> str:\n        """兜底的 wick 自我倾向文本。\n\n        防止动态人格补丁只插入了 self_profile_block 引用，\n        但没有插入变量定义/方法时导致崩溃。\n        """\n        context_info = context_info or {}\n        custom = str(getattr(self, "custom_prompt", "") or "").strip()\n        chat_id = str(context_info.get("chat_id", "") or "")\n\n        recent_lines: list[str] = []\n        try:\n            for item in self.recent_messages.get(chat_id, [])[-8:]:\n                if not isinstance(item, dict):\n                    continue\n                sender = str(item.get("sender_name", "") or item.get("sender_id", "") or "未知")\n                text = str(item.get("text", "") or "").strip()\n                reply = str(item.get("reply", "") or "").strip()\n                if text:\n                    recent_lines.append(f"{sender}: {text[:90]}")\n                if reply:\n                    recent_lines.append(f"wick: {reply[:90]}")\n        except Exception:\n            pass\n\n        lines = [\n            "你要像真人群友一样说话，可以有自己的想法，但不要暴露程序规则。",\n            "你的偏好、语气、在意点优先从人设和最近聊天里自然推断。",\n            "普通无关闲聊少插话；明确找你或话题确实碰到你的性格时，可以自然接一句。",\n        ]\n        if custom:\n            lines.append("人设原文：")\n            lines.append(custom[:1200])\n        if recent_lines:\n            lines.append("最近聊天：")\n            lines.extend(recent_lines[-8:])\n        return "\\n".join(lines)\n'


def method_range(src: str, method_name: str) -> tuple[int, int] | None:
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == method_name:
            if node.end_lineno is None:
                raise RuntimeError("AST 没有 end_lineno")
            return node.lineno, node.end_lineno
    return None


def insert_before_method(src: str, before_method: str, method_text: str) -> str:
    rng = method_range(src, before_method)
    if rng is None:
        raise RuntimeError(f"找不到插入位置：{before_method}")
    start, _end = rng
    lines = src.splitlines()
    new_lines = lines[: start - 1] + method_text.strip("\n").splitlines() + [""] + lines[start - 1:]
    return "\n".join(new_lines) + "\n"


def ensure_profile_method(src: str) -> str:
    if method_range(src, "_build_wick_self_profile_text") is not None:
        return src
    return insert_before_method(src, "_generate_reply_via_api", FALLBACK_PROFILE_METHOD)


def patch_generate_reply_self_profile_var(src: str) -> str:
    rng = method_range(src, "_generate_reply_via_api")
    if rng is None:
        raise RuntimeError("找不到 _generate_reply_via_api")

    start, end = rng
    lines = src.splitlines()
    method = lines[start - 1:end]

    # 找到首次使用 self_profile_block 的位置。
    target_idx = None
    for i, line in enumerate(method):
        if "self_profile_block" in line and "self_profile_block =" not in line:
            target_idx = i
            break

    if target_idx is None:
        print("没有发现 self_profile_block 使用点，可能已经修好了。")
        return src

    before_text = "\n".join(method[:target_idx])
    if "self_profile_block =" in before_text:
        print("self_profile_block 已经在使用前定义，跳过。")
        return src

    indent = method[target_idx][: len(method[target_idx]) - len(method[target_idx].lstrip())]

    insert = [
        f"{indent}try:",
        f"{indent}    self_profile_block = self._build_wick_self_profile_text(context_info)",
        f"{indent}except Exception as _self_profile_exc:",
        f"{indent}    self_profile_block = \"\"",
        f"{indent}    try:",
        f"{indent}        self.last_reply_api_error = \"self_profile 生成失败：\" + str(_self_profile_exc)",
        f"{indent}    except Exception:",
        f"{indent}        pass",
        "",
    ]

    method[target_idx:target_idx] = insert
    new_lines = lines[: start - 1] + method + lines[end:]
    return "\n".join(new_lines) + "\n"


def main() -> None:
    if not TARGET.exists():
        raise SystemExit(f"找不到文件：{TARGET}")

    src = TARGET.read_text(encoding="utf-8")
    backup = TARGET.with_suffix(".py.bak_fix_self_profile_block_v2")
    backup.write_text(src, encoding="utf-8")

    src = ensure_profile_method(src)
    src = patch_generate_reply_self_profile_var(src)

    compile(src, str(TARGET), "exec")
    TARGET.write_text(src, encoding="utf-8")

    print("✅ 已修复 self_profile_block 未定义")
    print("这次只修运行时崩溃，不改回复策略。")
    print(f"备份文件：{backup}")
    print("下一步：")
    print("  python -m py_compile .\\src\\clawmini\\tools\\qq_auto_reply.py")
    print("  python app.py")


if __name__ == "__main__":
    main()
