#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import ast
from pathlib import Path


PROJECT_ROOT = Path.cwd()
TARGET = PROJECT_ROOT / "src" / "clawmini" / "tools" / "qq_auto_reply.py"

HELPERS = '\n    def _normalize_bot_echo_text(self, text: str) -> str:\n        """归一化文本，用于识别群友是否在复读 bot 刚说过的话。"""\n        s = str(text or "")\n        s = re.sub(r"\\[CQ:[^\\]]+\\]", " ", s)\n        s = s.lower()\n        s = re.sub(r"\\s+", "", s)\n        s = s.strip("，。！？!?~～…、,.；;：:（）()[]【】「」『』\\"\'")\n        return s\n\n    def _is_echo_of_recent_bot_reply(self, chat_id: str, text: str) -> bool:\n        """如果群友几乎原样复读 bot 最近回复，不要每次都接。"""\n        current = self._normalize_bot_echo_text(text)\n        if len(current) < 6:\n            return False\n\n        try:\n            recent = self.recent_messages.get(chat_id, [])\n        except Exception:\n            recent = []\n\n        checked = 0\n        for item in reversed(recent[-16:]):\n            if not isinstance(item, dict):\n                continue\n            reply = str(item.get("reply", "") or "").strip()\n            if not reply:\n                continue\n            checked += 1\n            prev = self._normalize_bot_echo_text(reply)\n            if not prev:\n                continue\n\n            if current == prev:\n                return True\n\n            short, long = (current, prev) if len(current) <= len(prev) else (prev, current)\n            if len(short) >= 8 and short in long and len(short) / max(len(long), 1) >= 0.72:\n                return True\n\n            if checked >= 8:\n                break\n\n        return False\n'
NEW_SHOULD = '\n    def _should_reply_to_group_message(\n        self,\n        chat_id: str,\n        text: str,\n        mentioned: bool,\n        image_refs: list[str],\n        context_info: dict[str, Any] | None = None,\n    ) -> tuple[bool, str]:\n        """像真人一样决定要不要开口。\n\n        - @自己 / 回复自己：立即回。\n        - 非 @ 主动回复：只进候选队列，由 poll_pending 合并，避免并发多条刷屏。\n        - 群友复读 bot 最近发言：只记录，避免复制粘贴循环。\n        """\n        context_info = context_info or {}\n\n        if self._is_echo_of_recent_bot_reply(chat_id, text):\n            self.group_silence_count[chat_id] = self.group_silence_count.get(chat_id, 0) + 1\n            context_info["social_action"] = "observe"\n            context_info["social_gate_reason"] = "群友在复读我刚才的话，不继续接避免循环"\n            context_info["reply_relevance"] = 5\n            context_info["reply_relevance_reason"] = "复读 bot 最近回复"\n            return False, "群友在复读我刚才的话，不继续接避免循环。"\n\n        try:\n            score, reason = self._score_group_message_relevance(\n                text=text,\n                mentioned=mentioned,\n                image_refs=image_refs,\n                context_info=context_info,\n            )\n        except Exception:\n            score, reason = (0, "未能打分")\n\n        context_info["reply_relevance"] = score\n        context_info["reply_relevance_reason"] = reason\n\n        if mentioned or score >= 90:\n            self.group_silence_count[chat_id] = 0\n            return True, f"{reason} 立即回复。"\n\n        try:\n            if self._is_at_other_user_message(text) and not self._text_explicitly_about_self_bot(text):\n                self.group_silence_count[chat_id] = self.group_silence_count.get(chat_id, 0) + 1\n                context_info["social_action"] = "observe"\n                context_info["social_gate_reason"] = "@的是别人"\n                return False, "@的是别人，不抢话。"\n        except Exception:\n            pass\n\n        silence = self.group_silence_count.get(chat_id, 0)\n\n        decision = self._social_gate_decide_via_api(text, context_info)\n        action = str(decision.get("action", "observe"))\n        confidence = float(decision.get("confidence", 0.0) or 0.0)\n        gate_reason = str(decision.get("reason", "") or "")\n        gate_angle = str(decision.get("angle", "") or "")\n\n        context_info["social_action"] = action\n        context_info["social_confidence"] = confidence\n        context_info["social_gate_reason"] = gate_reason\n        context_info["social_gate_angle"] = gate_angle\n\n        if action == "reply" and confidence >= 0.45:\n            self.group_silence_count[chat_id] = silence + 1\n            context_info["reply_relevance"] = max(score, 65)\n            context_info["reply_relevance_reason"] = f"主动候选：{gate_reason}"\n            return False, f"wick 有自己的想法，进入合并候选：{gate_reason}"\n\n        if action == "candidate" and confidence >= 0.35:\n            self.group_silence_count[chat_id] = silence + 1\n            context_info["reply_relevance"] = max(score, 50)\n            context_info["reply_relevance_reason"] = f"候选想法：{gate_reason}"\n            return False, f"wick 有点想法但先观察：{gate_reason}"\n\n        self.group_silence_count[chat_id] = min(silence + 1, self.group_force_after_silence + 3)\n        return False, f"只观察：{gate_reason or reason}"\n'
NEW_ADD_BATCH = '\n    def _add_group_message_to_batch(\n        self,\n        chat_id: str,\n        sender_id: str,\n        text: str,\n        context_info: dict[str, Any],\n    ) -> tuple[bool, str]:\n        """把候选消息加入队列，但不在事件线程里立即发送。\n\n        统一交给 poll_pending 到期合并发送，避免多条非 @ 消息并发刷屏。\n        """\n        if self._is_echo_of_recent_bot_reply(chat_id, text):\n            return False, ""\n\n        score = int(context_info.get("reply_relevance", 0) or 0)\n        reason = str(context_info.get("reply_relevance_reason", "") or context_info.get("social_gate_reason", "") or "")\n        action = str(context_info.get("social_action", "") or "")\n        confidence = float(context_info.get("social_confidence", 0.0) or 0.0)\n        image_refs = list(context_info.get("image_refs", []))\n\n        if score < 45 and not (action in {"reply", "candidate"} and confidence >= 0.35):\n            return False, ""\n\n        now = datetime.now()\n        batch = self.pending_group_batches.get(chat_id)\n        if not batch:\n            wait_sec = int(getattr(self, "group_batch_max_wait_sec", 18) or 18)\n            wait_sec = max(8, min(wait_sec, 14))\n            batch = {\n                "due_at": now + timedelta(seconds=wait_sec),\n                "messages": [],\n                "context_info": dict(context_info),\n            }\n            self.pending_group_batches[chat_id] = batch\n\n        sender_name = context_info.get("sender_name", "") or sender_id\n        current = {\n            "sender_id": sender_id,\n            "sender_name": sender_name,\n            "text": text,\n            "image_refs": image_refs,\n            "reply_relevance": max(score, 50 if action in {"reply", "candidate"} else score),\n            "reply_relevance_reason": reason,\n            "social_action": action,\n            "social_confidence": confidence,\n            "social_gate_angle": str(context_info.get("social_gate_angle", "") or ""),\n        }\n\n        messages = batch.setdefault("messages", [])\n        if not messages or not (\n            str(messages[-1].get("sender_id", "")) == sender_id\n            and str(messages[-1].get("text", "")) == text\n        ):\n            messages.append(current)\n\n        deduped: list[dict[str, Any]] = []\n        seen_norm: set[str] = set()\n        for item in messages[-8:]:\n            if not isinstance(item, dict):\n                continue\n            norm = self._normalize_bot_echo_text(str(item.get("text", "") or ""))\n            key = f"{item.get(\'sender_id\',\'\')}|{norm}"\n            if norm and key in seen_norm:\n                continue\n            seen_norm.add(key)\n            deduped.append(item)\n\n        messages[:] = deduped[-6:]\n        batch["context_info"] = dict(context_info)\n        batch["context_info"]["batch_messages"] = list(messages)\n\n        return False, ""\n'


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
    for name in ("_normalize_bot_echo_text", "_is_echo_of_recent_bot_reply"):
        method_text = extract_one_method(HELPERS, name)
        if method_range(src, name) is not None:
            src = replace_method(src, name, method_text)
        else:
            src = insert_before(src, "_should_reply_to_group_message", method_text)
    return src


def patch_poll_guard(src: str) -> str:
    old = """            if has_gate_fields:
                relevant_messages = [
                    item for item in messages
                    if isinstance(item, dict)
                    and (
                        int(item.get("reply_relevance", 0) or 0) >= 45
                        or str(item.get("social_action", "")) in {"reply", "candidate"}
                    )
                ]
                strong_messages = [
                    item for item in messages
                    if isinstance(item, dict)
                    and (
                        int(item.get("reply_relevance", 0) or 0) >= 70
                        or (
                            str(item.get("social_action", "")) == "reply"
                            and float(item.get("social_confidence", 0.0) or 0.0) >= 0.50
                        )
                    )
                ]
                if not strong_messages and len(relevant_messages) < 2:
                    group_skipped += 1
                    continue"""
    new = """            if has_gate_fields:
                relevant_messages = [
                    item for item in messages
                    if isinstance(item, dict)
                    and (
                        int(item.get("reply_relevance", 0) or 0) >= 45
                        or str(item.get("social_action", "")) in {"reply", "candidate"}
                    )
                ]
                strong_messages = [
                    item for item in messages
                    if isinstance(item, dict)
                    and (
                        int(item.get("reply_relevance", 0) or 0) >= 60
                        or (
                            str(item.get("social_action", "")) == "reply"
                            and float(item.get("social_confidence", 0.0) or 0.0) >= 0.45
                        )
                    )
                ]
                # 单条高置信主动候选，到期也可以发；否则至少需要两条候选。
                if not strong_messages and len(relevant_messages) < 2:
                    group_skipped += 1
                    continue"""
    if old in src:
        return src.replace(old, new, 1)
    print("⚠️ 没找到 poll_pending 守门片段，已跳过；主合并逻辑仍会生效。")
    return src


def main() -> None:
    if not TARGET.exists():
        raise SystemExit(f"找不到文件：{TARGET}")

    src = TARGET.read_text(encoding="utf-8")
    backup = TARGET.with_suffix(".py.bak_coalesce_echo_guard")
    backup.write_text(src, encoding="utf-8")

    src = ensure_helpers(src)
    src = replace_method(src, "_should_reply_to_group_message", NEW_SHOULD)
    src = replace_method(src, "_add_group_message_to_batch", NEW_ADD_BATCH)
    src = patch_poll_guard(src)

    compile(src, str(TARGET), "exec")
    TARGET.write_text(src, encoding="utf-8")

    print("✅ 已修复主动回复刷屏和复读循环")
    print("非 @ 主动回复会先进候选队列，由 poll_pending 合并成一条。")
    print("群友复读 bot 最近回复时，只记录不继续接，避免复制粘贴循环。")
    print(f"备份文件：{backup}")
    print("下一步：")
    print("  python -m py_compile .\\src\\clawmini\\tools\\qq_auto_reply.py")
    print("  python app.py")


if __name__ == "__main__":
    main()
