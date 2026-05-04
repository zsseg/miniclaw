#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import ast
from pathlib import Path


PROJECT_ROOT = Path.cwd()
TARGET = PROJECT_ROOT / "src" / "clawmini" / "tools" / "qq_auto_reply.py"

HELPER_METHODS = '\n    def _text_refers_to_recent_image(self, text: str) -> bool:\n        clean = str(text or "").strip()\n        if not clean:\n            return False\n        image_words = [\n            "这个图", "这图", "这张图", "刚才的图", "上面的图", "上一张图",\n            "那个图", "那张图", "图片", "表情包", "表情", "图里", "图上",\n        ]\n        ask_words = [\n            "什么意思", "啥意思", "什么梗", "看懂", "看一下", "看看",\n            "是谁", "这是啥", "这是哪", "怎么回事", "解释", "意思",\n        ]\n        return any(w in clean for w in image_words) and any(w in clean for w in ask_words)\n\n    def _collect_recent_group_image_refs(self, chat_id: str, sender_id: str = "", limit: int = 3) -> list[str]:\n        """从待合并队列和最近历史里找同群最近图片。\n\n        用于这种场景：\n        群友先发一张图/表情包，下一句 @机器人 “这个图是什么意思”。\n        第二条消息本身没有 image_refs，但应该引用上一张图。\n        """\n        refs: list[str] = []\n        seen: set[str] = set()\n\n        def add_ref(value: Any) -> None:\n            ref = str(value or "").strip()\n            if not ref or ref in seen:\n                return\n            seen.add(ref)\n            refs.append(ref)\n\n        batch = self.pending_group_batches.get(chat_id)\n        if isinstance(batch, dict):\n            messages = batch.get("messages", [])\n            if isinstance(messages, list):\n                for item in reversed(messages):\n                    if not isinstance(item, dict):\n                        continue\n                    for ref in item.get("image_refs", []) or []:\n                        add_ref(ref)\n                        if len(refs) >= limit:\n                            return refs\n\n        history = self.recent_messages.get(chat_id, [])\n        if isinstance(history, list):\n            for item in reversed(history):\n                if not isinstance(item, dict):\n                    continue\n                # 优先同一发送者，但不强制，因为群里经常有人问别人刚发的图\n                for ref in item.get("image_refs", []) or []:\n                    add_ref(ref)\n                    if len(refs) >= limit:\n                        return refs\n\n        if sender_id:\n            user_key = f"{chat_id}|{sender_id}"\n            user_history = self.per_user_history.get(user_key, [])\n            if isinstance(user_history, list):\n                for item in reversed(user_history):\n                    if not isinstance(item, dict):\n                        continue\n                    for ref in item.get("image_refs", []) or []:\n                        add_ref(ref)\n                        if len(refs) >= limit:\n                            return refs\n\n        return refs\n'
NEW_RELEVANCE_AND_SHOULD = '\n    def _score_group_message_relevance(\n        self,\n        text: str,\n        mentioned: bool = False,\n        image_refs: list[str] | None = None,\n        context_info: dict[str, Any] | None = None,\n    ) -> tuple[int, str]:\n        """判断群消息和机器人/当前对话的相关度。"""\n        context_info = context_info or {}\n        image_refs = image_refs or []\n        clean_text = str(text or "").strip()\n        lower = clean_text.lower()\n\n        if mentioned:\n            return 100, "被@，强相关。"\n\n        reply_context = context_info.get("reply_context", {})\n        if isinstance(reply_context, dict):\n            reply_sender = str(reply_context.get("sender_id", "") or "").strip()\n            reply_text = str(reply_context.get("text", "") or "")\n            if reply_sender and reply_sender == str(self.self_user_id):\n                return 95, "正在回复机器人上一条消息。"\n            if any(name in reply_text.lower() for name in ("wick", "redamancy", "机器人", "bot", "猫娘", "小猫")):\n                return 75, "回复的原消息像是在聊机器人。"\n\n        bot_keywords = [\n            str(self.self_user_id).strip(),\n            "wick",\n            "redamancy",\n            "机器人",\n            "bot",\n            "小bot",\n            "ai",\n            "猫娘",\n            "猫猫",\n            "小猫",\n        ]\n        bot_keywords = [k.lower() for k in bot_keywords if k]\n        if any(k and k in lower for k in bot_keywords):\n            return 90, "点名机器人/人设关键词。"\n\n        direct_patterns = [\n            "你觉得", "你认为", "你说", "你看", "你来", "你能", "你会",\n            "帮我", "帮忙", "看看", "看一下", "分析一下", "解释一下",\n            "评价一下", "说说", "回一下", "答一下",\n        ]\n        if any(p in clean_text for p in direct_patterns):\n            return 78, "像是在直接让机器人回答。"\n\n        image_question_patterns = [\n            "这图", "这个图", "这张图", "刚才的图", "上面的图", "上一张图",\n            "图片", "表情包", "表情", "图里", "图上",\n            "啥意思", "什么意思", "什么梗", "看懂", "看一下", "看看",\n            "是谁", "这是啥", "这是哪", "怎么回事",\n        ]\n        if image_refs:\n            if any(p in clean_text for p in image_question_patterns) or context_info.get("recent_image_context"):\n                return 76, "正在问最近图片/表情包。"\n            if clean_text and clean_text not in {"图片消息", "图片", "[图片]"}:\n                return 48, "图片消息带普通配文。"\n            return 24, "纯图片/表情包，只作为背景记录。"\n\n        question_markers = ["？", "?", "怎么", "咋", "为什么", "为啥", "什么", "啥", "谁", "哪", "吗"]\n        if any(q in clean_text for q in question_markers):\n            return 42, "普通问题，但未明确找机器人。"\n\n        soft_chat_markers = ["修好", "好了", "成功", "寄了", "坏了", "笑死", "草", "绷", "逆天", "好耶", "yes"]\n        if any(k in lower for k in soft_chat_markers):\n            return 30, "普通情绪/状态消息。"\n\n        return 12, "普通群聊背景。"\n\n    def _should_reply_to_group_message(\n        self,\n        chat_id: str,\n        text: str,\n        mentioned: bool,\n        image_refs: list[str],\n        context_info: dict[str, Any] | None = None,\n    ) -> tuple[bool, str]:\n        """控制群聊回复频率：更关注和机器人有关的内容；图片也受频率/相关度控制。"""\n        score, score_reason = self._score_group_message_relevance(\n            text=text,\n            mentioned=mentioned,\n            image_refs=image_refs,\n            context_info=context_info,\n        )\n        silence = self.group_silence_count.get(chat_id, 0)\n\n        if score >= 90:\n            self.group_silence_count[chat_id] = 0\n            return True, f"{score_reason} 立即回复。"\n\n        if score >= 70:\n            if silence >= 1 or random.random() < 0.80:\n                self.group_silence_count[chat_id] = 0\n                return True, f"{score_reason} 高相关触发回复。"\n            self.group_silence_count[chat_id] = silence + 1\n            return False, f"{score_reason} 但本次进入合并队列，已连续记录 {silence + 1} 条。"\n\n        if score >= 45:\n            probability = 0.26 if image_refs else 0.18\n            if silence >= 3 or random.random() < probability:\n                self.group_silence_count[chat_id] = 0\n                return True, f"{score_reason} 中等相关概率触发回复。"\n            self.group_silence_count[chat_id] = silence + 1\n            return False, f"{score_reason} 暂不立即回复，已记录 {silence + 1} 条。"\n\n        if score >= 30:\n            if silence >= self.group_force_after_silence and random.random() < 0.28:\n                self.group_silence_count[chat_id] = 0\n                return True, f"{score_reason} 沉默较久，低频接话。"\n            if random.random() < self.group_reply_probability:\n                self.group_silence_count[chat_id] = 0\n                return True, f"{score_reason} 低概率接话。"\n            self.group_silence_count[chat_id] = silence + 1\n            return False, f"{score_reason} 作为背景记录，已连续记录 {silence + 1} 条。"\n\n        self.group_silence_count[chat_id] = min(silence + 1, self.group_force_after_silence + 2)\n        return False, f"{score_reason} 不主动回复，仅记录上下文。"\n'
NEW_ADD_BATCH = '\n    def _add_group_message_to_batch(\n        self,\n        chat_id: str,\n        sender_id: str,\n        text: str,\n        context_info: dict[str, Any],\n    ) -> tuple[bool, str]:\n        """把群消息加入待合并队列。\n\n        低相关消息只作为背景，只有出现和机器人有关/让机器人看图/明显提问的消息时才合并回复。\n        """\n        now = datetime.now()\n        batch = self.pending_group_batches.get(chat_id)\n        if not batch:\n            batch = {\n                "due_at": now + timedelta(seconds=self.group_batch_max_wait_sec),\n                "messages": [],\n                "context_info": dict(context_info),\n            }\n            self.pending_group_batches[chat_id] = batch\n\n        sender_name = context_info.get("sender_name", "") or sender_id\n        image_refs = list(context_info.get("image_refs", []))\n        relevance, relevance_reason = self._score_group_message_relevance(\n            text=text,\n            mentioned=False,\n            image_refs=image_refs,\n            context_info=context_info,\n        )\n\n        current = {\n            "sender_id": sender_id,\n            "sender_name": sender_name,\n            "text": text,\n            "image_refs": image_refs,\n            "reply_relevance": relevance,\n            "reply_relevance_reason": relevance_reason,\n        }\n\n        messages = batch.setdefault("messages", [])\n        if not messages or not (\n            str(messages[-1].get("sender_id", "")) == sender_id\n            and str(messages[-1].get("text", "")) == text\n        ):\n            messages.append(current)\n\n        messages[:] = messages[-6:]\n        batch["context_info"] = dict(context_info)\n        batch["context_info"]["batch_messages"] = list(messages)\n\n        relevant_messages = [\n            item for item in messages\n            if int(item.get("reply_relevance", 0) or 0) >= 45\n        ]\n        strong_messages = [\n            item for item in messages\n            if int(item.get("reply_relevance", 0) or 0) >= 70\n        ]\n\n        if not relevant_messages:\n            return False, ""\n\n        if strong_messages and len(messages) >= 2:\n            combined = self._build_group_batch_text(messages)\n            self.pending_group_batches.pop(chat_id, None)\n            context_info["batch_messages"] = list(messages)\n            return True, combined\n\n        if len(relevant_messages) >= 2 or len(messages) >= max(self.group_batch_min_messages, 4):\n            combined = self._build_group_batch_text(messages)\n            self.pending_group_batches.pop(chat_id, None)\n            context_info["batch_messages"] = list(messages)\n            return True, combined\n\n        return False, ""\n'
NEW_BUILD_BATCH = '\n    def _build_group_batch_text(self, messages: list[dict[str, Any]]) -> str:\n        """把几条群消息合并成一次给模型看的输入。"""\n        lines = [\n            "下面是群里刚刚连续聊的几句话。",\n            "你要先判断哪些内容是在和你/机器人聊天，哪些只是群友之间自己聊天。",\n            "回复策略：",\n            "1. 优先回应：@你、回复你、点名 wick/机器人/bot/猫娘、让你看图/解释图、直接问你的内容。",\n            "2. 对普通群友之间的闲聊，只当背景理解，除非很适合接一句，否则不要硬插话。",\n            "3. 如果图片只是表情包/纯图且没人问你，就少回复；如果有人问这图啥意思，再回复。",\n            "4. 不要逐条分别回复每个人，不要写成清单。",\n            "5. 尽量把共同意思合成一条自然群聊回复；最多两条，每条 20~70 字。",\n            "6. 像正常群友接话，简短自然，不要总结腔，不要刷存在感。",\n            "",\n            "群聊片段：",\n        ]\n\n        for item in messages[-6:]:\n            name = str(item.get("sender_name", "") or item.get("sender_id", "") or "未知")\n            uid = str(item.get("sender_id", "") or "未知")\n            msg_text = str(item.get("text", "") or "").strip()\n            image_refs = item.get("image_refs", []) or []\n            relevance = int(item.get("reply_relevance", 0) or 0)\n            reason = str(item.get("reply_relevance_reason", "") or "")\n            if image_refs:\n                msg_text += f" [附带{len(image_refs)}张图片]"\n            lines.append(f"- {name}(ID={uid})：{msg_text} ｜相关度={relevance}｜{reason}")\n\n        lines.append("")\n        lines.append("现在请只针对相关度较高、确实像是在找你聊天的内容自然回复；低相关内容只作为背景。")\n        return "\\n".join(lines)\n'


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


def insert_or_replace_helpers(src: str) -> str:
    if method_range(src, "_text_refers_to_recent_image") is not None:
        src = replace_method(src, "_text_refers_to_recent_image", HELPER_METHODS.split("    def _collect_recent_group_image_refs", 1)[0])
        collect_part = "    def _collect_recent_group_image_refs" + HELPER_METHODS.split("    def _collect_recent_group_image_refs", 1)[1]
        src = replace_method(src, "_collect_recent_group_image_refs", collect_part)
        return src

    rng = method_range(src, "_handle_message")
    if rng is None:
        raise RuntimeError("找不到 _handle_message")
    start, _end = rng
    lines = src.splitlines()
    new_lines = lines[: start - 1] + HELPER_METHODS.strip("\n").splitlines() + [""] + lines[start - 1:]
    return "\n".join(new_lines) + "\n"


def patch_init_defaults(src: str) -> str:
    src = src.replace("self.group_reply_probability = 0.12", "self.group_reply_probability = 0.04")
    src = src.replace("self.group_force_after_silence = 4", "self.group_force_after_silence = 6")
    src = src.replace("self.group_batch_min_messages = 3", "self.group_batch_min_messages = 4")
    src = src.replace("self.group_batch_max_wait_sec = 18", "self.group_batch_max_wait_sec = 22")
    return src


def patch_should_call(src: str) -> str:
    old = (
        '            should_reply, reply_reason = self._should_reply_to_group_message(\n'
        '                chat_id=chat_id,\n'
        '                text=text,\n'
        '                mentioned=mentioned,\n'
        '                image_refs=list(image_refs),\n'
        '            )'
    )
    new = (
        '            should_reply, reply_reason = self._should_reply_to_group_message(\n'
        '                chat_id=chat_id,\n'
        '                text=text,\n'
        '                mentioned=mentioned,\n'
        '                image_refs=list(image_refs),\n'
        '                context_info=context_info,\n'
        '            )'
    )
    if old in src:
        src = src.replace(old, new, 1)
    return src


def patch_recent_image_attach(src: str) -> str:
    marker = '            if mention_all:\n                return ToolResult(True, "检测到群@所有人，按规则不触发自动回复。")\n\n'
    insert = (
        '            if mention_all:\n'
        '                return ToolResult(True, "检测到群@所有人，按规则不触发自动回复。")\n\n'
        '            # 如果用户说“这个图是什么意思”，但当前消息本身没有图片，\n'
        '            # 就把同群最近一张图/表情包补进本次上下文，并清掉待合并队列，避免双回复。\n'
        '            if not image_refs and self._text_refers_to_recent_image(text):\n'
        '                recent_image_refs = self._collect_recent_group_image_refs(chat_id, sender_id)\n'
        '                if recent_image_refs:\n'
        '                    image_refs = list(recent_image_refs)\n'
        '                    context_info["image_refs"] = list(recent_image_refs)\n'
        '                    context_info["recent_image_context"] = True\n\n'
    )
    if 'recent_image_refs = self._collect_recent_group_image_refs(chat_id, sender_id)' in src:
        return src
    if marker not in src:
        raise RuntimeError("没找到 mention_all 后的插入位置")
    return src.replace(marker, insert, 1)


def patch_pop_pending_batch(src: str) -> str:
    old = (
        '            if source == "group" and should_reply:\n'
        '                self.pending_group_batches.pop(chat_id, None)\n'
        '                self.group_silence_count[chat_id] = 0'
    )
    new = (
        '            if source == "group" and should_reply:\n'
        '                pending_batch = self.pending_group_batches.pop(chat_id, None)\n'
        '                if isinstance(pending_batch, dict):\n'
        '                    pending_messages = pending_batch.get("messages", [])\n'
        '                    if isinstance(pending_messages, list) and pending_messages:\n'
        '                        context_info["batch_messages"] = list(pending_messages)\n'
        '                        pending_refs: list[str] = []\n'
        '                        for _item in pending_messages:\n'
        '                            if not isinstance(_item, dict):\n'
        '                                continue\n'
        '                            for _ref in _item.get("image_refs", []) or []:\n'
        '                                _ref = str(_ref).strip()\n'
        '                                if _ref and _ref not in pending_refs:\n'
        '                                    pending_refs.append(_ref)\n'
        '                        if pending_refs and not context_info.get("image_refs"):\n'
        '                            context_info["image_refs"] = pending_refs[:3]\n'
        '                            image_refs = pending_refs[:3]\n'
        '                            context_info["recent_image_context"] = True\n'
        '                self.group_silence_count[chat_id] = 0'
    )
    if old in src:
        return src.replace(old, new, 1)
    return src


def patch_cooldown_block(src: str) -> str:
    # 冷却期间不要再把高相关图片问答塞回合并队列，避免稍后又补一条。
    old = (
        '        if self._is_in_cooldown(chat_id):\n'
        '            # 触发冷却时也不要把普通群消息丢掉。\n'
        '            if source == "group" and not context_info.get("merge_batch"):'
    )
    new = (
        '        if self._is_in_cooldown(chat_id):\n'
        '            if source == "group":\n'
        '                score, _reason = self._score_group_message_relevance(text, False, list(context_info.get("image_refs", [])), context_info)\n'
        '                if score >= 70:\n'
        '                    self._remember_observed_group_message(chat_id=chat_id, sender_id=sender_id, text=text, context_info=context_info)\n'
        '                    return ToolResult(True, "触发频率控制：高相关消息已记录，但不再进入合并队列，避免重复回复。")\n'
        '            # 触发冷却时也不要把普通群消息丢掉。\n'
        '            if source == "group" and not context_info.get("merge_batch"):'
    )
    if old in src and "高相关消息已记录，但不再进入合并队列" not in src:
        return src.replace(old, new, 1)
    return src


def patch_prompt_text(src: str) -> str:
    old = "群聊里要结合上下文，合并共同话题，不要逐条复读。"
    new = (
        "群聊里要结合上下文，合并共同话题，不要逐条复读。"
        "优先回应明确在找你/机器人聊天的内容；普通群友之间的闲聊只当背景，不要硬插话。"
        "如果用户问“这个图/表情包是什么意思”，要优先结合最近一张图片理解。"
    )
    if old in src and new not in src:
        src = src.replace(old, new, 1)
    return src


def main() -> None:
    if not TARGET.exists():
        raise SystemExit(f"找不到文件：{TARGET}")

    src = TARGET.read_text(encoding="utf-8")
    backup = TARGET.with_suffix(".py.bak_recent_image_relevance")
    backup.write_text(src, encoding="utf-8")

    src = patch_init_defaults(src)
    src = insert_or_replace_helpers(src)
    src = replace_method(src, "_should_reply_to_group_message", NEW_RELEVANCE_AND_SHOULD)
    src = replace_method(src, "_add_group_message_to_batch", NEW_ADD_BATCH)
    src = replace_method(src, "_build_group_batch_text", NEW_BUILD_BATCH)
    src = patch_recent_image_attach(src)
    src = patch_should_call(src)
    src = patch_pop_pending_batch(src)
    src = patch_cooldown_block(src)
    src = patch_prompt_text(src)

    compile(src, str(TARGET), "exec")
    TARGET.write_text(src, encoding="utf-8")

    print("✅ 已修复最近图片问答与重复回复问题")
    print("现在：先发图再 @问“这个图什么意思”，会引用上一张图；纯表情包不再单独触发回复；高相关冷却时不再进入合并队列。")
    print(f"备份文件：{backup}")
    print("下一步：")
    print("  python -m py_compile .\\src\\clawmini\\tools\\qq_auto_reply.py")
    print("  python app.py")


if __name__ == "__main__":
    main()
