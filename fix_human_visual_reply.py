#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import ast
from pathlib import Path


PROJECT_ROOT = Path.cwd()
TARGET = PROJECT_ROOT / "src" / "clawmini" / "tools" / "qq_auto_reply.py"

HELPER = '\n    def _humanize_visual_meta_terms(self, reply: str) -> str:\n        """把视觉/识图相关的内部术语改成人类聊天口吻。\n\n        目标：群里最终看到的回复不要像“识图系统说明”，而要像真人接梗。\n        """\n        text = str(reply or "").strip()\n        if not text:\n            return ""\n\n        internal_patterns = [\n            r"图片视觉线索[（(][^）)]*[）)][:：]?.*?(?:。|$)",\n            r"低采信度[，,、 ]*仅供参考[，,、 ]*可能误读[:：]?.*?(?:。|$)",\n            r"使用规则[:：].*?(?:。|$)",\n            r"可见文字[:：]",\n            r"文字清晰度[:：]\\s*(?:高|中|低|无)[，,。 ]*",\n            r"采信度[:：]\\s*(?:高|中|低)[，,。 ]*",\n            r"可能情绪[:：]",\n            r"不确定点[:：]",\n            r"可见内容[:：]",\n            r"OCR[:：]?",\n        ]\n        for pat in internal_patterns:\n            text = re.sub(pat, "", text, flags=re.I | re.S).strip()\n\n        replacements = {\n            "这个表情包": "这个",\n            "这张表情包": "这个",\n            "那个表情包": "那个",\n            "表情包里的文字": "这句",\n            "表情包上写的": "这句",\n            "表情包文字": "这句",\n            "表情包": "这个",\n            "图里文字": "这句",\n            "图中文字": "这句",\n            "图片里的文字": "这句",\n            "图片上写的": "这句",\n            "可见文字": "这句",\n            "图里写着": "这句是",\n            "图片识别": "看起来",\n            "识图结果": "看起来",\n            "识图": "看",\n            "视觉线索": "看起来",\n            "低置信度": "不太确定",\n            "低采信度": "不太确定",\n            "采信度": "感觉",\n            "OCR": "",\n        }\n        for old, new in replacements.items():\n            text = text.replace(old, new)\n\n        text = re.sub(r"根据.{0,8}(?:看起来|来看)[，,]?", "", text)\n        text = re.sub(r"我(?:识别|检测|判断)到", "我看到", text)\n        text = re.sub(r"这句[:：]\\s*", "这句", text)\n        text = re.sub(r"\\s+", " ", text).strip()\n        text = re.sub(r"[（(]\\s*[）)]", "", text)\n        text = re.sub(r"[，,]\\s*[，,]+", "，", text)\n        text = re.sub(r"[。]\\s*[。]+", "。", text)\n        text = text.strip(" ，,。")\n\n        return text\n'
SANITIZE_WRAPPER = '\n    def _sanitize_reply_before_send(self, reply: str) -> str:\n        """发送前清理回复，并把视觉元话术改成人类口吻。"""\n        try:\n            cleaned = self._sanitize_reply_before_send_base(reply)\n        except Exception:\n            cleaned = str(reply or "").strip()\n\n        try:\n            cleaned = self._humanize_visual_meta_terms(cleaned)\n        except Exception:\n            pass\n\n        return cleaned\n'


def method_range(src: str, method_name: str) -> tuple[int, int] | None:
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == method_name:
            if node.end_lineno is None:
                raise RuntimeError("AST 没有 end_lineno")
            return node.lineno, node.end_lineno
    return None


def replace_method(src: str, method_name: str, method_text: str) -> str:
    rng = method_range(src, method_name)
    if rng is None:
        raise RuntimeError(f"找不到方法：{method_name}")
    start, end = rng
    lines = src.splitlines()
    new_lines = lines[: start - 1] + method_text.strip("\n").splitlines() + lines[end:]
    return "\n".join(new_lines) + "\n"


def insert_before(src: str, before_method: str, method_text: str) -> str:
    rng = method_range(src, before_method)
    if rng is None:
        raise RuntimeError(f"找不到插入位置：{before_method}")
    start, _end = rng
    lines = src.splitlines()
    new_lines = lines[: start - 1] + method_text.strip("\n").splitlines() + [""] + lines[start - 1:]
    return "\n".join(new_lines) + "\n"


def extract_one_method(block: str, method_name: str) -> str:
    wrapper = "class X:\n" + block
    tree = ast.parse(wrapper)
    lines = wrapper.splitlines()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == method_name and node.end_lineno is not None:
            return "\n".join(lines[node.lineno - 1:node.end_lineno])
    raise RuntimeError(f"block 里找不到 {method_name}")


def ensure_humanize_helper(src: str) -> str:
    method_text = extract_one_method(HELPER, "_humanize_visual_meta_terms")
    if method_range(src, "_humanize_visual_meta_terms") is not None:
        return replace_method(src, "_humanize_visual_meta_terms", method_text)

    before = "_sanitize_reply_before_send"
    if method_range(src, before) is None:
        before = "_build_reply_parts" if method_range(src, "_build_reply_parts") else "_send_via_gateway"
    return insert_before(src, before, method_text)


def wrap_sanitize(src: str) -> str:
    if method_range(src, "_sanitize_reply_before_send_base") is not None:
        if method_range(src, "_sanitize_reply_before_send") is not None:
            return replace_method(src, "_sanitize_reply_before_send", SANITIZE_WRAPPER)
        return insert_before(src, "_sanitize_reply_before_send_base", SANITIZE_WRAPPER)

    rng = method_range(src, "_sanitize_reply_before_send")
    if rng is None:
        before = "_send_via_gateway" if method_range(src, "_send_via_gateway") else "_build_reply_parts"
        fallback = """
    def _sanitize_reply_before_send_base(self, reply: str) -> str:
        return str(reply or "").strip()
"""
        src = insert_before(src, before, fallback)
        return insert_before(src, "_sanitize_reply_before_send_base", SANITIZE_WRAPPER)

    start, end = rng
    lines = src.splitlines()

    def_line_idx = start - 1
    lines[def_line_idx] = lines[def_line_idx].replace(
        "def _sanitize_reply_before_send(",
        "def _sanitize_reply_before_send_base(",
        1,
    )
    src2 = "\n".join(lines) + "\n"

    return insert_before(src2, "_sanitize_reply_before_send_base", SANITIZE_WRAPPER)


def patch_reply_prompts(src: str) -> str:
    addition = (
        " 最终发到群里的内容要像真人聊天，不要说“表情包/图片识别/OCR/可见文字/采信度/视觉线索/图中文字”这些系统分析词。"
        "如果看到了图上的字，直接像接梗一样回应那句话；不要解释自己看到了什么。"
    )
    if addition in src:
        return src

    markers = [
        "不要输出 Markdown、标题、编号、解释性前言。",
        "回复要短，像 QQ 聊天，不要写文章。",
        "不要强行解释图片本意",
        "图片识别结果只当低采信度视觉线索",
    ]
    for marker in markers:
        if marker in src:
            return src.replace(marker, marker + addition, 1)

    return src


def patch_sticker_context_reasons(src: str) -> str:
    replacements = {
        'context_info["reply_relevance_reason"] = f"表情包有清晰可见文字：{sticker_text}；像是在回应我刚才的话"':
            'context_info["reply_relevance_reason"] = f"对方发来的图里有一句清楚的话：{sticker_text}；可能是在接我刚才的话"',
        'context_info["social_gate_reason"] = "表情包文字可能是在回应 SELF；文字可信，含义仍需保守"':
            'context_info["social_gate_reason"] = "对方可能在用图里的话接梗；别解释图片本身，只像真人一样接话"',
        'return False, f"表情包文字候选：{sticker_text}"':
            'return False, f"图片文字候选：{sticker_text}"',
    }
    for old, new in replacements.items():
        src = src.replace(old, new)
    return src


def main() -> None:
    if not TARGET.exists():
        raise SystemExit(f"找不到文件：{TARGET}")

    src = TARGET.read_text(encoding="utf-8")
    backup = TARGET.with_suffix(".py.bak_human_visual_reply")
    backup.write_text(src, encoding="utf-8")

    src = ensure_humanize_helper(src)
    src = wrap_sanitize(src)
    src = patch_reply_prompts(src)
    src = patch_sticker_context_reasons(src)

    compile(src, str(TARGET), "exec")
    TARGET.write_text(src, encoding="utf-8")

    print("✅ 已修复：视觉/图片相关回复改成人类聊天口吻")
    print("1. 最终发到群里的内容会过滤“表情包/识图/OCR/可见文字/采信度”等元话术。")
    print("2. 图里有清晰文字时，bot 会像接梗一样回应，不会解释自己识别到了什么。")
    print("3. 不改主动开话题频率，不改识图采信度逻辑。")
    print(f"备份文件：{backup}")
    print("下一步：")
    print("  python -m py_compile .\\src\\clawmini\\tools\\qq_auto_reply.py")
    print("  python app.py")


if __name__ == "__main__":
    main()
