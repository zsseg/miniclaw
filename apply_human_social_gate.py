#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import ast
from pathlib import Path


PROJECT_ROOT = Path.cwd()
TARGET = PROJECT_ROOT / "src" / "clawmini" / "tools" / "qq_auto_reply.py"

HELPER_METHODS = '\n    def _text_refers_to_recent_image(self, text: str) -> bool:\n        clean = str(text or "").strip()\n        if not clean:\n            return False\n        image_words = [\n            "这个图", "这图", "这张图", "刚才的图", "上面的图", "上一张图",\n            "那个图", "那张图", "图片", "表情包", "表情", "图里", "图上",\n        ]\n        ask_words = [\n            "什么意思", "啥意思", "什么梗", "看懂", "看一下", "看看",\n            "是谁", "这是啥", "这是哪", "怎么回事", "解释", "意思",\n        ]\n        return any(w in clean for w in image_words) and any(w in clean for w in ask_words)\n\n    def _collect_recent_group_image_refs(self, chat_id: str, sender_id: str = "", limit: int = 3) -> list[str]:\n        refs: list[str] = []\n        seen: set[str] = set()\n\n        def add_ref(value: Any) -> None:\n            ref = str(value or "").strip()\n            if not ref or ref in seen:\n                return\n            seen.add(ref)\n            refs.append(ref)\n\n        batch = self.pending_group_batches.get(chat_id)\n        if isinstance(batch, dict):\n            for item in reversed(batch.get("messages", []) or []):\n                if not isinstance(item, dict):\n                    continue\n                for ref in item.get("image_refs", []) or []:\n                    add_ref(ref)\n                    if len(refs) >= limit:\n                        return refs\n\n        history = self.recent_messages.get(chat_id, [])\n        if isinstance(history, list):\n            for item in reversed(history):\n                if not isinstance(item, dict):\n                    continue\n                for ref in item.get("image_refs", []) or []:\n                    add_ref(ref)\n                    if len(refs) >= limit:\n                        return refs\n\n        if sender_id:\n            user_key = f"{chat_id}|{sender_id}"\n            user_history = self.per_user_history.get(user_key, [])\n            if isinstance(user_history, list):\n                for item in reversed(user_history):\n                    if not isinstance(item, dict):\n                        continue\n                    for ref in item.get("image_refs", []) or []:\n                        add_ref(ref)\n                        if len(refs) >= limit:\n                            return refs\n\n        return refs\n\n    def _recent_bot_topic_active(self, chat_id: str) -> bool:\n        bot_words = [\n            str(self.self_user_id).strip().lower(),\n            "wick", "redamancy", "机器人", "bot", "小bot", "猫娘", "猫猫",\n            "小猫", "程序猫", "回复概率", "触发", "模式", "oc", "人设",\n        ]\n        bot_words = [w for w in bot_words if w]\n        blobs: list[str] = []\n\n        batch = self.pending_group_batches.get(chat_id)\n        if isinstance(batch, dict):\n            for item in batch.get("messages", [])[-8:]:\n                if isinstance(item, dict):\n                    blobs.append(str(item.get("text", "")))\n\n        for item in self.recent_messages.get(chat_id, [])[-10:]:\n            if isinstance(item, dict):\n                blobs.append(str(item.get("text", "")))\n                blobs.append(str(item.get("reply", "")))\n\n        blob = "\\n".join(blobs).lower()\n        return any(word in blob for word in bot_words)\n\n    def _human_reply_threshold(self, score: int, context_info: dict[str, Any]) -> str:\n        if score >= 90:\n            return "must_reply"\n        if score >= 70:\n            return "candidate_reply"\n        if score >= 45:\n            return "soft_candidate"\n        return "observe_only"\n'
NEW_SCORE_AND_SHOULD = '\n    def _score_group_message_relevance(\n        self,\n        text: str,\n        mentioned: bool = False,\n        image_refs: list[str] | None = None,\n        context_info: dict[str, Any] | None = None,\n    ) -> tuple[int, str]:\n        """给群消息打相关度分：越像在找 wick/机器人聊天，越容易回复。"""\n        context_info = context_info or {}\n        image_refs = image_refs or []\n        clean_text = str(text or "").strip()\n        lower = clean_text.lower()\n        chat_id = str(context_info.get("chat_id", "") or "")\n\n        bot_keywords = [\n            str(self.self_user_id).strip(),\n            "wick", "redamancy", "机器人", "bot", "小bot", "ai",\n            "猫娘", "猫猫", "小猫", "程序猫",\n        ]\n        bot_keywords = [k.lower() for k in bot_keywords if k]\n\n        if mentioned:\n            return 100, "被@，明确在找我。"\n\n        reply_context = context_info.get("reply_context", {})\n        if isinstance(reply_context, dict):\n            reply_sender = str(reply_context.get("sender_id", "") or "").strip()\n            reply_text = str(reply_context.get("text", "") or "")\n            if reply_sender and reply_sender == str(self.self_user_id):\n                return 96, "正在回复我上一条消息。"\n            if any(k in reply_text.lower() for k in bot_keywords):\n                return 82, "回复的原消息在聊我。"\n\n        if any(k and k in lower for k in bot_keywords):\n            return 90, "点名我/机器人/人设关键词。"\n\n        # 最近已经在聊 bot 时，“他/这个/oc/模式/概率”这类代词也算相关。\n        bot_topic_words = [\n            "关于他", "让他", "他有", "他的", "给他", "它有", "它的", "给它",\n            "回复概率", "概率", "触发", "命令提示符", "at他", "@他",\n            "模式", "四种模式", "oc", "人设", "设定", "人格", "角色", "性格",\n            "抽风", "bug", "程序", "恢复", "回复方式",\n        ]\n        if any(w in clean_text for w in bot_topic_words) and self._recent_bot_topic_active(chat_id):\n            return 78, "最近在聊我的设定/触发/OC，本句相关。"\n\n        direct_patterns = [\n            "你觉得", "你认为", "你说", "你看", "你来", "你能", "你会",\n            "帮我", "帮忙", "看看", "看一下", "分析一下", "解释一下",\n            "评价一下", "说说", "回一下", "答一下",\n        ]\n        if any(p in clean_text for p in direct_patterns):\n            return 76, "像是在直接找我回答。"\n\n        image_question_patterns = [\n            "这图", "这个图", "这张图", "刚才的图", "上面的图", "上一张图",\n            "图片", "表情包", "表情", "图里", "图上",\n            "啥意思", "什么意思", "什么梗", "看懂", "看一下", "看看",\n            "是谁", "这是啥", "这是哪", "怎么回事",\n        ]\n        if image_refs:\n            if any(p in clean_text for p in image_question_patterns) or context_info.get("recent_image_context"):\n                return 78, "正在问最近图片/表情包。"\n            if clean_text and clean_text not in {"图片消息", "图片", "[图片]"}:\n                return 42, "图片消息带普通配文。"\n            return 18, "纯图片/表情包，只观察。"\n\n        question_markers = ["？", "?", "怎么", "咋", "为什么", "为啥", "什么", "啥", "谁", "哪", "吗"]\n        if any(q in clean_text for q in question_markers):\n            return 38, "普通问题，但没有明确找我。"\n\n        soft_chat_markers = ["修好", "好了", "成功", "寄了", "坏了", "笑死", "草", "绷", "逆天", "好耶", "yes"]\n        if any(k in lower for k in soft_chat_markers):\n            return 24, "普通情绪/状态，只观察为主。"\n\n        return 8, "普通群聊背景。"\n\n    def _should_reply_to_group_message(\n        self,\n        chat_id: str,\n        text: str,\n        mentioned: bool,\n        image_refs: list[str],\n        context_info: dict[str, Any] | None = None,\n    ) -> tuple[bool, str]:\n        """像真人一样决定要不要开口。"""\n        context_info = context_info or {}\n        score, reason = self._score_group_message_relevance(\n            text=text,\n            mentioned=mentioned,\n            image_refs=image_refs,\n            context_info=context_info,\n        )\n        context_info["reply_relevance"] = score\n        context_info["reply_relevance_reason"] = reason\n\n        silence = self.group_silence_count.get(chat_id, 0)\n\n        if score >= 90:\n            self.group_silence_count[chat_id] = 0\n            return True, f"{reason} 立即回复。"\n\n        if score >= 70:\n            probability = 0.72\n            if silence >= 2 or random.random() < probability:\n                self.group_silence_count[chat_id] = 0\n                return True, f"{reason} 高相关，像真人接话。"\n            self.group_silence_count[chat_id] = silence + 1\n            return False, f"{reason} 高相关但先观察一下，已记录 {silence + 1} 条。"\n\n        if score >= 45:\n            # 中相关不立即抢话，更多进入候选队列，看后续有没有人接。\n            if silence >= 4 and random.random() < 0.22:\n                self.group_silence_count[chat_id] = 0\n                return True, f"{reason} 沉默较久，低频接一句。"\n            self.group_silence_count[chat_id] = silence + 1\n            return False, f"{reason} 作为候选观察，已记录 {silence + 1} 条。"\n\n        # 无关/普通背景：只观察，不进入回复候选。\n        self.group_silence_count[chat_id] = min(silence + 1, self.group_force_after_silence + 3)\n        return False, f"{reason} 不主动回复。"\n'
NEW_ADD_BATCH = '\n    def _add_group_message_to_batch(\n        self,\n        chat_id: str,\n        sender_id: str,\n        text: str,\n        context_info: dict[str, Any],\n    ) -> tuple[bool, str]:\n        """把相关消息加入回复候选队列；普通背景只记录，不会进队列。"""\n        score = int(context_info.get("reply_relevance", 0) or 0)\n        reason = str(context_info.get("reply_relevance_reason", "") or "")\n        image_refs = list(context_info.get("image_refs", []))\n\n        if score <= 0:\n            score, reason = self._score_group_message_relevance(\n                text=text,\n                mentioned=False,\n                image_refs=image_refs,\n                context_info=context_info,\n            )\n\n        # 关键：低相关内容不进入 pending_group_batches，避免 poll_pending 过一会儿硬插话。\n        if score < 45:\n            return False, ""\n\n        now = datetime.now()\n        batch = self.pending_group_batches.get(chat_id)\n        if not batch:\n            batch = {\n                "due_at": now + timedelta(seconds=self.group_batch_max_wait_sec),\n                "messages": [],\n                "context_info": dict(context_info),\n            }\n            self.pending_group_batches[chat_id] = batch\n\n        sender_name = context_info.get("sender_name", "") or sender_id\n        current = {\n            "sender_id": sender_id,\n            "sender_name": sender_name,\n            "text": text,\n            "image_refs": image_refs,\n            "reply_relevance": score,\n            "reply_relevance_reason": reason,\n        }\n\n        messages = batch.setdefault("messages", [])\n        if not messages or not (\n            str(messages[-1].get("sender_id", "")) == sender_id\n            and str(messages[-1].get("text", "")) == text\n        ):\n            messages.append(current)\n\n        messages[:] = messages[-6:]\n        batch["context_info"] = dict(context_info)\n        batch["context_info"]["batch_messages"] = list(messages)\n\n        strong = [m for m in messages if int(m.get("reply_relevance", 0) or 0) >= 70]\n        medium = [m for m in messages if int(m.get("reply_relevance", 0) or 0) >= 45]\n\n        # 强相关通常已经即时回复；如果没即时回，等两条上下文再合并，避免重复。\n        if len(strong) >= 1 and len(messages) >= 2:\n            combined = self._build_group_batch_text(messages)\n            self.pending_group_batches.pop(chat_id, None)\n            context_info["batch_messages"] = list(messages)\n            return True, combined\n\n        # 中相关要至少两条，才像真人接一嘴。\n        if len(medium) >= 2:\n            combined = self._build_group_batch_text(messages)\n            self.pending_group_batches.pop(chat_id, None)\n            context_info["batch_messages"] = list(messages)\n            return True, combined\n\n        return False, ""\n'
NEW_BUILD_BATCH = '\n    def _build_group_batch_text(self, messages: list[dict[str, Any]]) -> str:\n        """把候选群消息合成一次给模型看的输入。"""\n        lines = [\n            "下面是群里刚刚连续聊的几句话。",\n            "你不是客服，也不是每句都要回复的机器人。你是一个在群里旁听的真实群友 wick。",\n            "先判断：哪些话是在找你/聊你，哪些只是群友之间互相聊天。",\n            "回复策略：",\n            "1. 只回应和你有关、有人问你、有人让你看图、或正在聊你 OC/人设/模式的内容。",\n            "2. 普通闲聊只当背景，不要硬插话。",\n            "3. 纯表情、纯图片没人问时不要回复。",\n            "4. 如果你没有新的想法，就宁可不说。",\n            "5. 回复要像 QQ 群友，短，自然，有一点自己的态度，但不要解释程序机制。",\n            "",\n            "群聊片段：",\n        ]\n\n        for item in messages[-6:]:\n            name = str(item.get("sender_name", "") or item.get("sender_id", "") or "未知")\n            uid = str(item.get("sender_id", "") or "未知")\n            msg_text = str(item.get("text", "") or "").strip()\n            image_refs = item.get("image_refs", []) or []\n            relevance = int(item.get("reply_relevance", 0) or 0)\n            reason = str(item.get("reply_relevance_reason", "") or "")\n            if image_refs:\n                msg_text += f" [附带{len(image_refs)}张图片]"\n            lines.append(f"- {name}(ID={uid})：{msg_text} ｜相关度={relevance}｜{reason}")\n\n        lines.append("")\n        lines.append("现在只针对相关内容接一两句；不要逐条回复，不要总结，不要暴露触发规则。")\n        return "\\n".join(lines)\n'
NEW_HANDLE_MESSAGE = '\n    def _handle_message(self, arguments: dict[str, Any]) -> ToolResult:\n        if not self.enabled or self.paused:\n            return ToolResult(True, "自动回复已禁用或处于安静模式。")\n\n        source = str(arguments.get("source", "private"))\n        chat_id = str(arguments.get("chat_id", ""))\n        sender_id = str(arguments.get("sender_id", "anon"))\n        raw_text = str(arguments.get("text", ""))\n        text = sanitize_prompt_injection(raw_text)\n        image_refs = self._extract_image_refs(arguments)\n\n        context_info = {\n            "source": source,\n            "chat_id": chat_id,\n            "sender_id": sender_id,\n            "sender_name": str(arguments.get("sender_name", "")).strip(),\n            "sender_avatar": str(arguments.get("sender_avatar", "")).strip(),\n            "group_name": str(arguments.get("group_name", "")).strip(),\n            "group_avatar": str(arguments.get("group_avatar", "")).strip(),\n            "image_refs": list(image_refs),\n            "reply_context": arguments.get("reply_context", {}),\n        }\n\n        if source == "group":\n            mentioned = bool(arguments.get("mentioned", False))\n            mention_all = bool(arguments.get("mention_all", False))\n\n            if chat_id not in self.target_group_ids:\n                return ToolResult(True, "非目标群，已忽略。")\n\n            if mention_all:\n                return ToolResult(True, "检测到群@所有人，按规则不触发自动回复。")\n\n            # 先发图，再问“这个图什么意思”时，把最近图片补进本次上下文。\n            if not image_refs and self._text_refers_to_recent_image(text):\n                recent_image_refs = self._collect_recent_group_image_refs(chat_id, sender_id)\n                if recent_image_refs:\n                    image_refs = list(recent_image_refs)\n                    context_info["image_refs"] = list(recent_image_refs)\n                    context_info["recent_image_context"] = True\n\n            should_reply, reply_reason = self._should_reply_to_group_message(\n                chat_id=chat_id,\n                text=text,\n                mentioned=mentioned,\n                image_refs=list(image_refs),\n                context_info=context_info,\n            )\n\n            if should_reply:\n                # 如果之前有候选队列，把它当背景吸收，但不要让它稍后再补发一条。\n                pending_batch = self.pending_group_batches.pop(chat_id, None)\n                if isinstance(pending_batch, dict):\n                    pending_messages = pending_batch.get("messages", [])\n                    if isinstance(pending_messages, list) and pending_messages:\n                        context_info["batch_messages"] = list(pending_messages)\n                        pending_refs: list[str] = []\n                        for item in pending_messages:\n                            if not isinstance(item, dict):\n                                continue\n                            for ref in item.get("image_refs", []) or []:\n                                ref = str(ref).strip()\n                                if ref and ref not in pending_refs:\n                                    pending_refs.append(ref)\n                        if pending_refs and not context_info.get("image_refs"):\n                            context_info["image_refs"] = pending_refs[:3]\n                            image_refs = pending_refs[:3]\n                            context_info["recent_image_context"] = True\n                self.group_silence_count[chat_id] = 0\n\n            if not should_reply:\n                self._remember_observed_group_message(\n                    chat_id=chat_id,\n                    sender_id=sender_id,\n                    text=text,\n                    context_info=context_info,\n                )\n\n                score = int(context_info.get("reply_relevance", 0) or 0)\n\n                if score < 45:\n                    return ToolResult(True, reply_reason + " 已记录为背景，不进入合并回复队列。")\n\n                batch_ready, batch_text = self._add_group_message_to_batch(\n                    chat_id=chat_id,\n                    sender_id=sender_id,\n                    text=text,\n                    context_info=context_info,\n                )\n                if not batch_ready:\n                    return ToolResult(True, reply_reason + " 已记录为回复候选，等待更多相关上下文。")\n\n                text = batch_text\n                context_info["merge_batch"] = True\n                self.pending_group_batches.pop(chat_id, None)\n                self.group_silence_count[chat_id] = 0\n\n        elif source == "private":\n            if not self.private_enabled:\n                return ToolResult(True, "私聊自动回复未启用。")\n            manual_replied = bool(arguments.get("manual_replied", False))\n            waited_sec = int(arguments.get("waited_sec", self.private_delay_sec + 1))\n            if manual_replied:\n                self.pending_private.pop(chat_id, None)\n                return ToolResult(True, f"私聊任务已取消：{chat_id}")\n            if waited_sec <= self.private_delay_sec:\n                due_at = datetime.now() + timedelta(seconds=max(self.private_delay_sec - waited_sec, 1))\n                self.pending_private[chat_id] = {\n                    "sender_id": sender_id,\n                    "text": text,\n                    "due_at": due_at,\n                    "source": source,\n                    "sender_name": str(arguments.get("sender_name", "")).strip(),\n                    "sender_avatar": str(arguments.get("sender_avatar", "")).strip(),\n                    "group_name": str(arguments.get("group_name", "")).strip(),\n                    "group_avatar": str(arguments.get("group_avatar", "")).strip(),\n                    "image_refs": list(image_refs),\n                }\n                remain = max(self.private_delay_sec - waited_sec, 1)\n                return ToolResult(True, f"私聊已进入等待队列：{chat_id}，约 {remain} 秒后触发。")\n        else:\n            return ToolResult(False, f"未知消息来源: {source}")\n\n        if self._is_in_cooldown(chat_id):\n            if source == "group":\n                self._remember_observed_group_message(\n                    chat_id=chat_id,\n                    sender_id=sender_id,\n                    text=text,\n                    context_info=context_info,\n                )\n                score = int(context_info.get("reply_relevance", 0) or 0)\n                if score >= 70:\n                    return ToolResult(True, "触发频率控制：高相关消息已记录，但不进入合并队列，避免重复回复。")\n                if 45 <= score < 70 and not context_info.get("merge_batch"):\n                    self._add_group_message_to_batch(\n                        chat_id=chat_id,\n                        sender_id=sender_id,\n                        text=text,\n                        context_info=context_info,\n                    )\n                    return ToolResult(True, "触发频率控制：中相关消息已记录为候选。")\n            return ToolResult(True, "触发频率控制：30秒内不重复回复。")\n\n        safe_sender = f"user_{abs(hash(sender_id)) % 10000}"\n        reply_parts = self._build_reply_parts(text, context_info=context_info)\n        if not reply_parts:\n            return ToolResult(False, "未生成可发送的回复内容。")\n\n        send_result = self._send_via_gateway(chat_id=chat_id, reply=self._sanitize_reply_before_send(reply_parts[0]), message_type=source)\n        if not send_result.success:\n            return send_result\n\n        sent_parts = [self._sanitize_reply_before_send(reply_parts[0])]\n        for extra_part in reply_parts[1:]:\n            extra_result = self._send_via_gateway(chat_id=chat_id, reply=extra_part, message_type=source)\n            if not extra_result.success:\n                return extra_result\n            sent_parts.append(self._sanitize_reply_before_send(extra_part))\n\n        if source == "group":\n            self.pending_group_batches.pop(chat_id, None)\n\n        self.last_auto_reply[chat_id] = datetime.now()\n        combined_reply = "\\n\\n".join(sent_parts)\n        self._append_log(chat_id, safe_sender, text, combined_reply)\n        self._remember_recent_exchange(chat_id, source, sender_id, text, combined_reply, context_info)\n\n        meta = dict(send_result.meta) if isinstance(send_result.meta, dict) else {}\n        meta.update(\n            {\n                "chat_id": chat_id,\n                "message_type": source,\n                "reply": combined_reply,\n                "reply_parts": sent_parts,\n                "reply_count": len(sent_parts),\n                "reply_source": self.last_reply_api_source,\n                "reply_api_error": self.last_reply_api_error,\n                "reply_api_endpoint": self.last_reply_api_endpoint,\n                "reply_api_provider": self.reply_api_provider,\n                "reply_api_model": self.reply_api_model,\n                "reply_api_base_url": self.reply_api_base_url,\n            }\n        )\n        reply_summary = combined_reply if len(sent_parts) == 1 else f"{len(sent_parts)} 条消息"\n        return ToolResult(True, f"已自动回复到 {chat_id}: {reply_summary}", meta)\n'


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


def insert_method_before(src: str, before_method: str, method_text: str) -> str:
    rng = method_range(src, before_method)
    if rng is None:
        raise RuntimeError(f"找不到插入位置：{before_method}")
    start, _end = rng
    lines = src.splitlines()
    new_lines = lines[: start - 1] + method_text.strip("\n").splitlines() + [""] + lines[start - 1:]
    return "\n".join(new_lines) + "\n"


def ensure_helpers(src: str) -> str:
    for name in ("_text_refers_to_recent_image", "_collect_recent_group_image_refs", "_recent_bot_topic_active", "_human_reply_threshold"):
        if method_range(src, name) is not None:
            src = replace_method(src, name, _extract_one_method(HELPER_METHODS, name))
    missing = [
        name for name in ("_text_refers_to_recent_image", "_collect_recent_group_image_refs", "_recent_bot_topic_active", "_human_reply_threshold")
        if method_range(src, name) is None
    ]
    if missing:
        src = insert_method_before(src, "_handle_message", HELPER_METHODS)
    return src


def _extract_one_method(block: str, method_name: str) -> str:
    tree = ast.parse("class X:\n" + block)
    lines = ("class X:\n" + block).splitlines()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == method_name and node.end_lineno is not None:
            # remove leading class line and preserve method indentation
            return "\n".join(lines[node.lineno - 1:node.end_lineno])
    raise RuntimeError(f"helper block 里找不到 {method_name}")


def replace_or_insert(src: str, method_name: str, method_text: str, before_method: str) -> str:
    if method_range(src, method_name) is not None:
        return replace_method(src, method_name, method_text)
    return insert_method_before(src, before_method, method_text)


def patch_init_defaults(src: str) -> str:
    # 已改过就不重复影响；没改过就收敛为更像真人的安静值。
    src = src.replace("self.group_reply_probability = 0.12", "self.group_reply_probability = 0.03")
    src = src.replace("self.group_reply_probability = 0.04", "self.group_reply_probability = 0.03")
    src = src.replace("self.group_force_after_silence = 4", "self.group_force_after_silence = 7")
    src = src.replace("self.group_force_after_silence = 6", "self.group_force_after_silence = 7")
    src = src.replace("self.group_batch_min_messages = 3", "self.group_batch_min_messages = 4")
    src = src.replace("self.group_batch_max_wait_sec = 18", "self.group_batch_max_wait_sec = 24")
    src = src.replace("self.group_batch_max_wait_sec = 22", "self.group_batch_max_wait_sec = 24")
    return src


def patch_poll_pending_guard(src: str) -> str:
    if "人格化群聊合并守门" in src:
        return src
    target = (
        '            if self._is_in_cooldown(chat_id):\n'
        '                group_skipped += 1\n'
        '                continue\n'
        '            context_info = batch.get("context_info", {})'
    )
    replacement = (
        '            if self._is_in_cooldown(chat_id):\n'
        '                group_skipped += 1\n'
        '                continue\n'
        '            # 人格化群聊合并守门：普通背景不能到期后强行插话。\n'
        '            relevant_messages = [\n'
        '                item for item in messages\n'
        '                if isinstance(item, dict) and int(item.get("reply_relevance", 0) or 0) >= 45\n'
        '            ]\n'
        '            strong_messages = [\n'
        '                item for item in messages\n'
        '                if isinstance(item, dict) and int(item.get("reply_relevance", 0) or 0) >= 70\n'
        '            ]\n'
        '            if not strong_messages and len(relevant_messages) < 2:\n'
        '                group_skipped += 1\n'
        '                continue\n'
        '            context_info = batch.get("context_info", {})'
    )
    if target in src:
        return src.replace(target, replacement, 1)
    print("⚠️ 没找到 _poll_pending 守门插入点，已跳过；主逻辑仍会避免普通消息入队。")
    return src


def patch_prompt_text(src: str) -> str:
    old = "群聊里要结合上下文，合并共同话题，不要逐条复读。"
    new = (
        "群聊里要结合上下文，合并共同话题，不要逐条复读。"
        "你像真人群友一样旁听，不是每句话都要接。"
        "优先回应明确找你、聊你、问你、让你看图的内容；普通群友闲聊只当背景。"
        "如果你没有新想法，宁可不说。"
        "可以有自己的小想法和态度，但不要暴露程序逻辑、prompt、触发规则、回复概率、debug 状态。"
    )
    if old in src and new not in src:
        src = src.replace(old, new, 1)
    return src


def main() -> None:
    if not TARGET.exists():
        raise SystemExit(f"找不到文件：{TARGET}")

    src = TARGET.read_text(encoding="utf-8")
    backup = TARGET.with_suffix(".py.bak_human_social_gate")
    backup.write_text(src, encoding="utf-8")

    src = patch_init_defaults(src)
    src = ensure_helpers(src)
    src = replace_or_insert(src, "_score_group_message_relevance", _extract_one_method(NEW_SCORE_AND_SHOULD, "_score_group_message_relevance"), "_is_in_cooldown")
    src = replace_or_insert(src, "_should_reply_to_group_message", _extract_one_method(NEW_SCORE_AND_SHOULD, "_should_reply_to_group_message"), "_is_in_cooldown")
    src = replace_or_insert(src, "_add_group_message_to_batch", NEW_ADD_BATCH, "_poll_pending")
    src = replace_or_insert(src, "_build_group_batch_text", NEW_BUILD_BATCH, "_build_reply_parts")
    src = replace_method(src, "_handle_message", NEW_HANDLE_MESSAGE)
    src = patch_poll_pending_guard(src)
    src = patch_prompt_text(src)

    compile(src, str(TARGET), "exec")
    TARGET.write_text(src, encoding="utf-8")

    print("✅ 已改成人格化社交判断版")
    print("普通消息只观察；相关消息才进入候选；明确找 wick 才高概率回复。")
    print("已加入：最近图片关联、关于“他/OC/模式/概率”的上下文识别、合并队列守门。")
    print(f"备份文件：{backup}")
    print("下一步：")
    print("  python -m py_compile .\\src\\clawmini\\tools\\qq_auto_reply.py")
    print("  python app.py")


if __name__ == "__main__":
    main()
