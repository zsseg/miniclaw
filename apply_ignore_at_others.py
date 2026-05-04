#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import ast
from pathlib import Path


PROJECT_ROOT = Path.cwd()
TARGET = PROJECT_ROOT / "src" / "clawmini" / "tools" / "qq_auto_reply.py"

NEW_AT_HELPERS = '\n    def _extract_mentioned_user_ids_from_text(self, text: str) -> list[str]:\n        # 从 CQ 文本里提取被 @ 的 QQ 号。\n        ids: list[str] = []\n        for match in re.finditer(r"\\[CQ:at,[^\\]]*qq=([^,\\]]+)", str(text or "")):\n            value = match.group(1).strip()\n            if value and value not in ids:\n                ids.append(value)\n        return ids\n\n    def _is_at_other_user_message(self, text: str) -> bool:\n        # 判断这条消息是否主要是在 @ 别人。\n        at_ids = self._extract_mentioned_user_ids_from_text(text)\n        if not at_ids:\n            return False\n        self_id = str(self.self_user_id or "").strip()\n        return any(qid not in {"all", self_id} for qid in at_ids)\n\n    def _text_explicitly_about_self_bot(self, text: str) -> bool:\n        # @别人时，只有明确提到 wick/自己，才允许继续接话。\n        clean = str(text or "").lower()\n        self_id = str(self.self_user_id or "").strip().lower()\n        self_names = [\n            self_id,\n            "wick",\n            "redamancy",\n            "redamancy.",\n            "小猫娘",\n            "猫娘wick",\n            "wick酱",\n            "这个wick",\n        ]\n        return any(name and name in clean for name in self_names)\n'
NEW_SCORE = '\n    def _score_group_message_relevance(\n        self,\n        text: str,\n        mentioned: bool = False,\n        image_refs: list[str] | None = None,\n        context_info: dict[str, Any] | None = None,\n    ) -> tuple[int, str]:\n        # 给群消息打相关度分：越像在找 wick/机器人聊天，越容易回复。\n        # 特别规则：@ 别人的消息默认不抢答，除非同时明确提到 wick/自己。\n        context_info = context_info or {}\n        image_refs = image_refs or []\n        clean_text = str(text or "").strip()\n        lower = clean_text.lower()\n        chat_id = str(context_info.get("chat_id", "") or "")\n\n        if mentioned:\n            return 100, "被@，明确在找我。"\n\n        reply_context = context_info.get("reply_context", {})\n        if isinstance(reply_context, dict):\n            reply_sender = str(reply_context.get("sender_id", "") or "").strip()\n            reply_text = str(reply_context.get("text", "") or "")\n            if reply_sender and reply_sender == str(self.self_user_id):\n                return 96, "正在回复我上一条消息。"\n\n        # @ 别人的消息，默认不要回。\n        # 例如“@小小豆 讲讲你的四种模式”是在找别人，不是找 wick。\n        if self._is_at_other_user_message(clean_text) and not self._text_explicitly_about_self_bot(clean_text):\n            return 4, "@的是别人，不抢话。"\n\n        bot_keywords = [\n            str(self.self_user_id).strip(),\n            "wick", "redamancy", "机器人", "bot", "小bot", "ai",\n            "猫娘", "猫猫", "小猫", "程序猫",\n        ]\n        bot_keywords = [k.lower() for k in bot_keywords if k]\n\n        if isinstance(reply_context, dict):\n            reply_text = str(reply_context.get("text", "") or "")\n            if any(k in reply_text.lower() for k in bot_keywords):\n                return 82, "回复的原消息在聊我。"\n\n        if any(k and k in lower for k in bot_keywords):\n            return 90, "点名我/机器人/人设关键词。"\n\n        bot_topic_words = [\n            "关于他", "让他", "他有", "他的", "给他", "它有", "它的", "给它",\n            "回复概率", "概率", "触发", "命令提示符", "at他", "@他",\n            "模式", "四种模式", "oc", "人设", "设定", "人格", "角色", "性格",\n            "抽风", "bug", "程序", "恢复", "回复方式",\n        ]\n        if any(w in clean_text for w in bot_topic_words) and self._recent_bot_topic_active(chat_id):\n            return 78, "最近在聊我的设定/触发/OC，本句相关。"\n\n        direct_patterns = [\n            "你觉得", "你认为", "你说", "你看", "你来", "你能", "你会",\n            "帮我", "帮忙", "看看", "看一下", "分析一下", "解释一下",\n            "评价一下", "说说", "回一下", "答一下",\n        ]\n        if any(p in clean_text for p in direct_patterns):\n            return 76, "像是在直接找我回答。"\n\n        image_question_patterns = [\n            "这图", "这个图", "这张图", "刚才的图", "上面的图", "上一张图",\n            "图片", "表情包", "表情", "图里", "图上",\n            "啥意思", "什么意思", "什么梗", "看懂", "看一下", "看看",\n            "是谁", "这是啥", "这是哪", "怎么回事",\n        ]\n        if image_refs:\n            if any(p in clean_text for p in image_question_patterns) or context_info.get("recent_image_context"):\n                return 78, "正在问最近图片/表情包。"\n            if clean_text and clean_text not in {"图片消息", "图片", "[图片]"}:\n                return 42, "图片消息带普通配文。"\n            return 18, "纯图片/表情包，只观察。"\n\n        question_markers = ["？", "?", "怎么", "咋", "为什么", "为啥", "什么", "啥", "谁", "哪", "吗"]\n        if any(q in clean_text for q in question_markers):\n            return 38, "普通问题，但没有明确找我。"\n\n        soft_chat_markers = ["修好", "好了", "成功", "寄了", "坏了", "笑死", "草", "绷", "逆天", "好耶", "yes"]\n        if any(k in lower for k in soft_chat_markers):\n            return 24, "普通情绪/状态，只观察为主。"\n\n        return 8, "普通群聊背景。"\n'


def method_range(src: str, method_name: str) -> tuple[int, int] | None:
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == method_name:
            if node.end_lineno is None:
                raise RuntimeError("AST 没有 end_lineno")
            return node.lineno, node.end_lineno
    return None


def replace_method(src: str, method_name: str, new_method: str) -> str:
    rng = method_range(src, method_name)
    if rng is None:
        raise RuntimeError(f"找不到方法：{method_name}")
    start, end = rng
    lines = src.splitlines()
    new_lines = lines[: start - 1] + new_method.strip("\n").splitlines() + lines[end:]
    return "\n".join(new_lines) + "\n"


def insert_before_method(src: str, before_method: str, block: str) -> str:
    rng = method_range(src, before_method)
    if rng is None:
        raise RuntimeError(f"找不到插入位置：{before_method}")
    start, _end = rng
    lines = src.splitlines()
    new_lines = lines[: start - 1] + block.strip("\n").splitlines() + [""] + lines[start - 1:]
    return "\n".join(new_lines) + "\n"


def extract_one_method(block: str, method_name: str) -> str:
    wrapper = "class X:\n" + block
    tree = ast.parse(wrapper)
    lines = wrapper.splitlines()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == method_name and node.end_lineno is not None:
            return "\n".join(lines[node.lineno - 1:node.end_lineno])
    raise RuntimeError(f"helper block 里找不到 {method_name}")


def ensure_at_helpers(src: str) -> str:
    for name in (
        "_extract_mentioned_user_ids_from_text",
        "_is_at_other_user_message",
        "_text_explicitly_about_self_bot",
    ):
        method_text = extract_one_method(NEW_AT_HELPERS, name)
        if method_range(src, name) is not None:
            src = replace_method(src, name, method_text)
        else:
            target = "_score_group_message_relevance" if method_range(src, "_score_group_message_relevance") else "_handle_message"
            src = insert_before_method(src, target, method_text)
    return src


def main() -> None:
    if not TARGET.exists():
        raise SystemExit(f"找不到文件：{TARGET}")

    src = TARGET.read_text(encoding="utf-8")
    backup = TARGET.with_suffix(".py.bak_ignore_at_others")
    backup.write_text(src, encoding="utf-8")

    src = ensure_at_helpers(src)
    src = replace_method(src, "_score_group_message_relevance", NEW_SCORE)

    compile(src, str(TARGET), "exec")
    TARGET.write_text(src, encoding="utf-8")

    print("✅ 已优化：@别人的消息默认不回复")
    print("规则：@别人时除非明确提到 wick/Redamancy/自己，否则只记录背景不抢话。")
    print(f"备份文件：{backup}")
    print("下一步：")
    print("  python -m py_compile .\\src\\clawmini\\tools\\qq_auto_reply.py")
    print("  python app.py")


if __name__ == "__main__":
    main()
