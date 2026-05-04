#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import ast
from pathlib import Path


PROJECT_ROOT = Path.cwd()
TARGET = PROJECT_ROOT / "src" / "clawmini" / "tools" / "qq_auto_reply.py"

HELPERS = '\n    def _clean_text_for_social_pattern(self, text: str) -> str:\n        """清理 CQ 码，用于判断抽象接龙/歌词/复读结构。"""\n        s = str(text or "")\n        s = re.sub(r"\\[CQ:[^\\]]+\\]", " ", s)\n        s = re.sub(r"\\s+", "", s)\n        return s.strip()\n\n    def _looks_like_unaddressed_repetition_chain(\n        self,\n        chat_id: str,\n        sender_id: str,\n        text: str,\n        context_info: dict[str, Any] | None = None,\n    ) -> bool:\n        """判断是否像“抽象接龙/歌词/排比”，且没有明确指向机器人。\n\n        这不是写死人设，而是社交结构判断：\n        同一个人连续发短句，句式高度相似，并且没有 @ / 明确指向 SELF，\n        这类通常只是群友自娱自乐，不应主动接。\n        """\n        context_info = context_info or {}\n        clean = self._clean_text_for_social_pattern(text)\n        if not clean or len(clean) > 18:\n            return False\n\n        if context_info.get("mentioned") or context_info.get("explicit_self"):\n            return False\n\n        try:\n            if self._text_explicitly_about_self_bot(text):\n                return False\n        except Exception:\n            pass\n\n        # 纯表情/纯图片交给已有图片/表情逻辑，这里不处理。\n        if not re.sub(r"\\[CQ:[^\\]]+\\]", "", str(text or "")).strip():\n            return False\n\n        same_sender_recent: list[str] = []\n\n        try:\n            batch = self.pending_group_batches.get(str(chat_id), {})\n            if isinstance(batch, dict):\n                for item in batch.get("messages", [])[-8:]:\n                    if not isinstance(item, dict):\n                        continue\n                    if str(item.get("sender_id", "")) == str(sender_id):\n                        t = self._clean_text_for_social_pattern(str(item.get("text", "")))\n                        if t:\n                            same_sender_recent.append(t)\n        except Exception:\n            pass\n\n        try:\n            for item in self.recent_messages.get(str(chat_id), [])[-12:]:\n                if not isinstance(item, dict):\n                    continue\n                if str(item.get("sender_id", "")) == str(sender_id):\n                    t = self._clean_text_for_social_pattern(str(item.get("text", "")))\n                    if t:\n                        same_sender_recent.append(t)\n        except Exception:\n            pass\n\n        same_sender_recent.append(clean)\n\n        # 只看最近同一人的短句。\n        short_lines = [x for x in same_sender_recent[-6:] if 1 <= len(x) <= 18]\n        if len(short_lines) < 3:\n            return False\n\n        # 同前缀接龙：例如 “什么样的心情 / 什么样的年纪 / 什么样的欢愉 / 什么样的哭泣”\n        for prefix_len in (2, 3, 4, 5):\n            prefix = clean[:prefix_len]\n            if len(prefix) < prefix_len:\n                continue\n            count = sum(1 for x in short_lines if x.startswith(prefix))\n            if count >= 3:\n                return True\n\n        # 相似短句模板：长度接近，首尾结构类似。\n        last3 = short_lines[-3:]\n        if len(last3) == 3:\n            starts = [x[:2] for x in last3 if len(x) >= 2]\n            if len(starts) == 3 and len(set(starts)) == 1:\n                return True\n\n        return False\n\n    def _downgrade_pending_candidates(\n        self,\n        chat_id: str,\n        sender_id: str = "",\n        factor: float = 0.25,\n        reason: str = "",\n    ) -> None:\n        """降低已有候选权重，而不是硬删除。\n\n        当后续消息显示这是一串抽象接龙/无指向发言时，\n        之前误入候选的消息应当自然降权，避免 poll_pending 继续发送旧候选。\n        """\n        try:\n            batch = self.pending_group_batches.get(str(chat_id))\n            if not isinstance(batch, dict):\n                return\n            messages = batch.get("messages", [])\n            if not isinstance(messages, list):\n                return\n\n            now = datetime.now()\n            for item in messages:\n                if not isinstance(item, dict):\n                    continue\n                if sender_id and str(item.get("sender_id", "")) != str(sender_id):\n                    continue\n                old = float(item.get("candidate_weight", 0.0) or 0.0)\n                if old <= 0:\n                    try:\n                        old = self._candidate_base_weight(item)\n                    except Exception:\n                        old = 0.2\n                item["candidate_weight"] = max(0.0, old * factor)\n                item["downgraded_reason"] = reason or "后续消息显示该候选相关性下降"\n                item["downgraded_at"] = now.isoformat(timespec="seconds")\n\n            batch["messages"] = messages\n        except Exception:\n            pass\n'
CANDIDATE_BASE = '\n    def _candidate_base_weight(self, item: dict[str, Any]) -> float:\n        """候选基础权重。\n\n        只根据“显式性/相关度/模型置信度/消息形态”计算，不写死人设或兴趣点。\n        """\n        try:\n            relevance = float(item.get("reply_relevance", 0) or 0) / 100.0\n        except Exception:\n            relevance = 0.0\n\n        try:\n            confidence = float(item.get("social_confidence", 0.0) or 0.0)\n        except Exception:\n            confidence = 0.0\n\n        action = str(item.get("social_action", "") or "")\n        reason = str(item.get("reply_relevance_reason", "") or item.get("social_gate_reason", "") or "")\n        text = str(item.get("text", "") or "")\n\n        weight = max(relevance, confidence)\n\n        if action == "reply":\n            weight += 0.14\n        elif action == "candidate":\n            weight += 0.05\n\n        # 明确找自己更重要。\n        if item.get("mentioned") or item.get("explicit_self"):\n            weight += 0.30\n\n        # 只是图片背景/表情背景，权重大幅降低。\n        if item.get("recent_image_context") and not item.get("explicit_image_question"):\n            weight *= 0.50\n\n        visible_text = re.sub(r"\\[CQ:[^\\]]+\\]", "", text).strip()\n        if "[CQ:face" in text and not visible_text:\n            weight *= 0.25\n        if "[CQ:image" in text and not visible_text:\n            weight *= 0.18\n\n        # “破冰/无人接话”不是和 SELF 相关的理由，降低主动性。\n        if any(k in reason for k in ("破冰", "无人接话", "自顾自", "抽象问题", "未明确指向")):\n            if not item.get("mentioned") and not item.get("explicit_self"):\n                weight *= 0.45\n\n        # 已被后续消息降权。\n        if item.get("downgraded_reason"):\n            weight *= 0.45\n\n        return max(0.0, min(weight, 1.35))\n'
CANDIDATE_DECAY = '\n    def _candidate_decayed_weight(self, item: dict[str, Any], now: datetime | None = None) -> float:\n        """候选权重随时间衰减。\n\n        默认半衰期调长到 45 秒：不容易忘，但旧候选仍会逐渐变成背景。\n        """\n        now = now or datetime.now()\n        base = float(item.get("candidate_weight", 0.0) or 0.0)\n        if base <= 0:\n            base = self._candidate_base_weight(item)\n\n        created_at = self._candidate_timestamp(item, default=now) if hasattr(self, "_candidate_timestamp") else now\n        try:\n            age_sec = max(0.0, (now - created_at).total_seconds())\n        except Exception:\n            age_sec = 0.0\n\n        try:\n            half_life = float(os.getenv("QQ_CANDIDATE_HALF_LIFE_SEC", "45"))\n        except Exception:\n            half_life = 45.0\n        half_life = max(12.0, min(half_life, 180.0))\n\n        decay = 0.5 ** (age_sec / half_life)\n        weight = base * decay\n\n        # 不是直接忘记，而是很旧的普通候选只当低权背景。\n        if age_sec > 150 and not item.get("mentioned") and not item.get("explicit_self"):\n            weight *= 0.35\n\n        return max(0.0, min(weight, 1.5))\n'
SHOULD_REPLY = '\n    def _should_reply_to_group_message(\n        self,\n        chat_id: str,\n        text: str,\n        mentioned: bool,\n        image_refs: list[str],\n        context_info: dict[str, Any] | None = None,\n    ) -> tuple[bool, str]:\n        """像真人一样决定要不要开口。\n\n        这版重点：\n        - 不写死人设；\n        - 抽象接龙/歌词/排比不会因为前面候选而继续触发；\n        - 非 @ 主动回复仍进候选，由权值衰减决定是否发。\n        """\n        context_info = context_info or {}\n        context_info["mentioned"] = bool(mentioned)\n\n        # 纯图片/纯表情背景不要主动回复。\n        try:\n            if image_refs and not mentioned and self._is_plain_image_or_sticker_message(text, image_refs) and not self._message_has_explicit_image_question(text):\n                context_info["reply_relevance"] = 8\n                context_info["reply_relevance_reason"] = "纯图片/表情包，只作为背景。"\n                return False, "纯图片/表情包，只作为背景，不主动回复。"\n        except Exception:\n            pass\n\n        # 群友复读 bot 近期回复，不继续接。\n        try:\n            if self._is_echo_of_recent_bot_reply(chat_id, text):\n                self.group_silence_count[chat_id] = self.group_silence_count.get(chat_id, 0) + 1\n                context_info["social_action"] = "observe"\n                context_info["social_gate_reason"] = "群友在复读我刚才的话，不继续接避免循环"\n                context_info["reply_relevance"] = 5\n                context_info["reply_relevance_reason"] = "复读 bot 最近回复"\n                return False, "群友在复读我刚才的话，不继续接避免循环。"\n        except Exception:\n            pass\n\n        sender_id = str(context_info.get("sender_id", "") or "")\n        # 抽象接龙/歌词/排比：如果没有明确指向 SELF，就降权已有候选并观察。\n        try:\n            if self._looks_like_unaddressed_repetition_chain(chat_id, sender_id, text, context_info):\n                self._downgrade_pending_candidates(\n                    chat_id=chat_id,\n                    sender_id=sender_id,\n                    factor=0.18,\n                    reason="后续消息像无指向接龙/歌词/排比，不应继续主动接。",\n                )\n                self.group_silence_count[chat_id] = min(self.group_silence_count.get(chat_id, 0) + 1, self.group_force_after_silence + 3)\n                context_info["social_action"] = "observe"\n                context_info["social_gate_reason"] = "同一用户连续短句接龙/排比，未明确指向 SELF"\n                context_info["reply_relevance"] = 12\n                context_info["reply_relevance_reason"] = "无指向接龙/排比"\n                return False, "只观察：同一用户连续短句接龙/排比，未明确指向我。"\n        except Exception:\n            pass\n\n        try:\n            score, reason = self._score_group_message_relevance(\n                text=text,\n                mentioned=mentioned,\n                image_refs=image_refs,\n                context_info=context_info,\n            )\n        except Exception:\n            score, reason = (0, "未能打分")\n\n        context_info["reply_relevance"] = score\n        context_info["reply_relevance_reason"] = reason\n\n        if mentioned or score >= 90:\n            self.group_silence_count[chat_id] = 0\n            context_info["explicit_self"] = True\n            return True, f"{reason} 立即回复。"\n\n        try:\n            if self._is_at_other_user_message(text) and not self._text_explicitly_about_self_bot(text):\n                self.group_silence_count[chat_id] = self.group_silence_count.get(chat_id, 0) + 1\n                context_info["social_action"] = "observe"\n                context_info["social_gate_reason"] = "@的是别人"\n                return False, "@的是别人，不抢话。"\n        except Exception:\n            pass\n\n        silence = self.group_silence_count.get(chat_id, 0)\n\n        decision = self._social_gate_decide_via_api(text, context_info)\n        action = str(decision.get("action", "observe"))\n        confidence = float(decision.get("confidence", 0.0) or 0.0)\n        gate_reason = str(decision.get("reason", "") or "")\n        gate_angle = str(decision.get("angle", "") or "")\n\n        # “破冰/无人接话”不是强相关理由；除非明确提到自己，否则不要主动候选。\n        if action in {"reply", "candidate"} and any(k in gate_reason for k in ("破冰", "无人接话", "自顾自", "抽象问题", "未明确指向")):\n            try:\n                if not self._text_explicitly_about_self_bot(text):\n                    action = "observe"\n                    confidence = min(confidence, 0.20)\n            except Exception:\n                action = "observe"\n                confidence = min(confidence, 0.20)\n\n        context_info["social_action"] = action\n        context_info["social_confidence"] = confidence\n        context_info["social_gate_reason"] = gate_reason\n        context_info["social_gate_angle"] = gate_angle\n\n        if action == "reply" and confidence >= 0.52:\n            self.group_silence_count[chat_id] = silence + 1\n            context_info["reply_relevance"] = max(score, 65)\n            context_info["reply_relevance_reason"] = f"主动候选：{gate_reason}"\n            return False, f"wick 有自己的想法，进入合并候选：{gate_reason}"\n\n        if action == "candidate" and confidence >= 0.44:\n            self.group_silence_count[chat_id] = silence + 1\n            context_info["reply_relevance"] = max(score, 50)\n            context_info["reply_relevance_reason"] = f"候选想法：{gate_reason}"\n            return False, f"wick 有点想法但先观察：{gate_reason}"\n\n        self.group_silence_count[chat_id] = min(silence + 1, self.group_force_after_silence + 3)\n        return False, f"只观察：{gate_reason or reason}"\n'


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


def ensure_helpers(src: str) -> str:
    for name in (
        "_clean_text_for_social_pattern",
        "_looks_like_unaddressed_repetition_chain",
        "_downgrade_pending_candidates",
    ):
        method_text = extract_one_method(HELPERS, name)
        if method_range(src, name) is not None:
            src = replace_method(src, name, method_text)
        else:
            target = "_should_reply_to_group_message" if method_range(src, "_should_reply_to_group_message") else "_handle_message"
            src = insert_before(src, target, method_text)
    return src


def main() -> None:
    if not TARGET.exists():
        raise SystemExit(f"找不到文件：{TARGET}")

    src = TARGET.read_text(encoding="utf-8")
    backup = TARGET.with_suffix(".py.bak_memory_chain_fix")
    backup.write_text(src, encoding="utf-8")

    src = ensure_helpers(src)

    if method_range(src, "_candidate_base_weight") is not None:
        src = replace_method(src, "_candidate_base_weight", CANDIDATE_BASE)

    if method_range(src, "_candidate_decayed_weight") is not None:
        src = replace_method(src, "_candidate_decayed_weight", CANDIDATE_DECAY)

    if method_range(src, "_should_reply_to_group_message") is not None:
        src = replace_method(src, "_should_reply_to_group_message", SHOULD_REPLY)
    else:
        raise RuntimeError("找不到 _should_reply_to_group_message")

    compile(src, str(TARGET), "exec")
    TARGET.write_text(src, encoding="utf-8")

    print("✅ 已修复：记忆衰减过快 + 抽象接龙误触发")
    print("1. 候选半衰期默认从 22 秒调到 45 秒，不会那么快忘。")
    print("2. 同一用户连续短句接龙/排比且未指向机器人时，会降权旧候选并观察。")
    print("3. “破冰/无人接话”不再作为强主动回复理由。")
    print(f"备份文件：{backup}")
    print("下一步：")
    print("  python -m py_compile .\\src\\clawmini\\tools\\qq_auto_reply.py")
    print("  python app.py")
    print()
    print("可调参数：")
    print('  $env:QQ_CANDIDATE_HALF_LIFE_SEC="45"')


if __name__ == "__main__":
    main()
