#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import ast
from pathlib import Path


PROJECT_ROOT = Path.cwd()
TARGET = PROJECT_ROOT / "src" / "clawmini" / "tools" / "qq_auto_reply.py"

DYNAMIC_HELPERS = '\n    def _build_wick_self_profile_text(self, context_info: dict[str, Any] | None = None) -> str:\n        """给模型看的“自我倾向”。\n\n        重点：不要在代码里写死 wick 喜欢什么。\n        让模型从 custom_prompt 和最近对话中自行抽取偏好、雷点、好奇点。\n        """\n        context_info = context_info or {}\n        custom = str(getattr(self, "custom_prompt", "") or "").strip()\n\n        chat_id = str(context_info.get("chat_id", "") or "")\n        recent_lines: list[str] = []\n        for item in self.recent_messages.get(chat_id, [])[-8:]:\n            if not isinstance(item, dict):\n                continue\n            speaker = str(item.get("speaker", "") or item.get("sender_id", "") or "未知")\n            text = str(item.get("text", "") or "").strip()\n            reply = str(item.get("reply", "") or "").strip()\n            if text:\n                recent_lines.append(f"{speaker}: {text[:80]}")\n            if reply:\n                recent_lines.append(f"wick: {reply[:80]}")\n\n        lines = [\n            "你要像真人一样从自己的人设里自然长出偏好，而不是按固定关键词触发。",\n            "你的兴趣、在意点、雷点、口癖、审美，都应从下面的人设和最近聊天里自行推断。",\n            "如果群聊内容碰到了你的偏好/好奇/在意点，你可以低频主动说一句自己的看法。",\n            "如果只是别人互相聊天、@别人、纯表情、纯图片，不要抢话。",\n            "不要说自己是按关键词、概率、规则、prompt 触发的。",\n        ]\n        if custom:\n            lines.append("人设原文：")\n            lines.append(custom[:1200])\n        if recent_lines:\n            lines.append("最近聊天片段：")\n            lines.extend(recent_lines[-10:])\n        return "\\n".join(lines)\n\n    def _strip_cq_for_social_gate(self, text: str) -> str:\n        clean = str(text or "")\n        clean = re.sub(r"\\[CQ:at,[^\\]]+\\]", "", clean)\n        clean = re.sub(r"\\[CQ:(face|image|forward)[^\\]]+\\]", "", clean)\n        clean = re.sub(r"\\s+", " ", clean).strip()\n        return clean\n\n    def _is_obvious_non_speech_message(self, text: str, context_info: dict[str, Any] | None = None) -> bool:\n        """明显不该主动说话的消息：纯表情、纯图、纯转发、明显 @ 别人。"""\n        context_info = context_info or {}\n        raw = str(text or "")\n        clean = self._strip_cq_for_social_gate(raw)\n\n        if not clean:\n            return True\n\n        # 如果已经有“@ 别人”辅助函数，就用它。@ 别人时默认不抢话。\n        try:\n            if self._is_at_other_user_message(raw) and not self._text_explicitly_about_self_bot(raw):\n                return True\n        except Exception:\n            pass\n\n        return False\n\n    def _social_gate_decide_via_api(\n        self,\n        text: str,\n        context_info: dict[str, Any] | None = None,\n    ) -> dict[str, Any]:\n        """让模型判断 wick 要不要主动说话。\n\n        返回：\n        {\n          "action": "reply" | "candidate" | "observe",\n          "confidence": 0~1,\n          "reason": "...",\n          "angle": "如果要说话，从哪个角度说"\n        }\n\n        这个 gate 不写死兴趣。它让模型从 custom_prompt 与最近聊天中判断：\n        wick 是否真的有自己的想法值得冒泡。\n        """\n        context_info = context_info or {}\n\n        provider = self.reply_api_provider.strip().lower()\n        api_key = self.reply_api_key.strip()\n        if provider not in {"openai", "deepseek", "qwen"} or not api_key:\n            return {"action": "observe", "confidence": 0.0, "reason": "没有可用 API 做社交判断", "angle": ""}\n\n        raw_text = str(text or "")\n        if self._is_obvious_non_speech_message(raw_text, context_info):\n            return {"action": "observe", "confidence": 0.0, "reason": "明显不是该主动说话的消息", "angle": ""}\n\n        if self.reply_api_model.strip():\n            model_name = self.reply_api_model.strip()\n        elif provider == "deepseek":\n            model_name = "deepseek-v4-pro"\n        elif provider == "qwen":\n            model_name = "qwen-plus"\n        else:\n            model_name = "gpt-4o-mini"\n\n        base_url = self.reply_api_base_url.strip()\n        if provider == "deepseek" and not base_url:\n            base_url = "https://api.deepseek.com"\n        if provider == "deepseek" and base_url.rstrip("/").endswith("/v1"):\n            base_url = base_url.rstrip("/")[:-3].rstrip("/")\n        if provider == "openai" and not base_url:\n            base_url = "https://api.openai.com/v1"\n        if provider == "qwen" and not base_url:\n            base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"\n\n        endpoint = base_url.rstrip("/") + "/chat/completions"\n\n        self_profile = self._build_wick_self_profile_text(context_info)\n        context_block = self._build_context_block(text, context_info)\n\n        gate_prompt = (\n            "你在帮 QQ 群里的猫娘 wick 判断：现在要不要开口。\\n"\n            "重要：不要靠固定关键词。请从 wick 的人设、最近聊天、当前话题里判断她是否真的有自己的想法。\\n"\n            "如果只是别人互相聊天、@别人、纯表情、纯图片、或者 wick 说了也没新东西，就 observe。\\n"\n            "如果当前话题碰到 wick 的性格、偏好、好奇点、审美、雷点，且插一句会像真人群友，就 reply 或 candidate。\\n"\n            "reply = 现在就说；candidate = 可以等几句合并再说；observe = 只看不说。\\n"\n            "只输出 JSON，不要解释，不要 Markdown。\\n"\n            \'格式：{"action":"reply|candidate|observe","confidence":0.0,"reason":"短原因","angle":"如果开口，从什么角度说"}\'\n        )\n\n        user_gate = (\n            f"wick 自我倾向：\\n{self_profile[:1800]}\\n\\n"\n            f"当前上下文：\\n{context_block[:2200]}\\n\\n"\n            f"当前消息：{raw_text[:500]}"\n        )\n\n        payload: dict[str, Any] = {\n            "model": model_name,\n            "messages": [\n                {"role": "system", "content": gate_prompt},\n                {"role": "user", "content": user_gate},\n            ],\n            "max_tokens": 180,\n        }\n\n        if provider == "deepseek":\n            # gate 只要快速判断，不要带采样参数；DeepSeek V4 可以使用 thinking，但给很小输出。\n            if model_name.startswith("deepseek-v4"):\n                payload["thinking"] = {"type": "enabled"}\n                payload["reasoning_effort"] = "high"\n                payload["max_tokens"] = 260\n        else:\n            payload["temperature"] = 0.2\n\n        req = urllib.request.Request(\n            endpoint,\n            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),\n            headers={\n                "Authorization": f"Bearer {api_key}",\n                "Content-Type": "application/json",\n            },\n            method="POST",\n        )\n\n        try:\n            with urllib.request.urlopen(req, timeout=25) as resp:\n                body = json.loads(resp.read().decode("utf-8"))\n            content = str(body.get("choices", [{}])[0].get("message", {}).get("content", "") or "").strip()\n\n            # 容错：模型可能在 JSON 外包一点文字。\n            match = re.search(r"\\{[\\s\\S]*\\}", content)\n            if match:\n                content = match.group(0)\n\n            data = json.loads(content)\n            action = str(data.get("action", "observe")).strip().lower()\n            if action not in {"reply", "candidate", "observe"}:\n                action = "observe"\n\n            try:\n                confidence = float(data.get("confidence", 0.0))\n            except Exception:\n                confidence = 0.0\n            confidence = max(0.0, min(1.0, confidence))\n\n            return {\n                "action": action,\n                "confidence": confidence,\n                "reason": str(data.get("reason", ""))[:120],\n                "angle": str(data.get("angle", ""))[:180],\n            }\n        except Exception as exc:\n            return {"action": "observe", "confidence": 0.0, "reason": f"gate失败：{exc}", "angle": ""}\n'
NEW_SHOULD = '\n    def _should_reply_to_group_message(\n        self,\n        chat_id: str,\n        text: str,\n        mentioned: bool,\n        image_refs: list[str],\n        context_info: dict[str, Any] | None = None,\n    ) -> tuple[bool, str]:\n        """像真人一样决定要不要开口。\n\n        这版不靠固定兴趣词。\n        明确 @/回复我 仍然直接回；其他消息交给模型做“社交判断”：\n        wick 是否从自己的人设和最近聊天里产生了想法。\n        """\n        context_info = context_info or {}\n\n        # 明确找我，直接回复。\n        score, reason = self._score_group_message_relevance(\n            text=text,\n            mentioned=mentioned,\n            image_refs=image_refs,\n            context_info=context_info,\n        )\n        context_info["reply_relevance"] = score\n        context_info["reply_relevance_reason"] = reason\n\n        if mentioned or score >= 90:\n            self.group_silence_count[chat_id] = 0\n            return True, f"{reason} 立即回复。"\n\n        # 明显 @ 别人，不抢话。\n        try:\n            if self._is_at_other_user_message(text) and not self._text_explicitly_about_self_bot(text):\n                self.group_silence_count[chat_id] = self.group_silence_count.get(chat_id, 0) + 1\n                context_info["social_action"] = "observe"\n                context_info["social_gate_reason"] = "@的是别人"\n                return False, "@的是别人，不抢话。"\n        except Exception:\n            pass\n\n        silence = self.group_silence_count.get(chat_id, 0)\n\n        # 纯图/纯表情/纯转发不主动说。\n        if self._is_obvious_non_speech_message(text, context_info) and not image_refs:\n            self.group_silence_count[chat_id] = min(silence + 1, self.group_force_after_silence + 3)\n            context_info["social_action"] = "observe"\n            context_info["social_gate_reason"] = "纯低信息消息"\n            return False, "低信息消息，只观察。"\n\n        decision = self._social_gate_decide_via_api(text, context_info)\n        action = str(decision.get("action", "observe"))\n        confidence = float(decision.get("confidence", 0.0) or 0.0)\n        gate_reason = str(decision.get("reason", "") or "")\n        gate_angle = str(decision.get("angle", "") or "")\n\n        context_info["social_action"] = action\n        context_info["social_confidence"] = confidence\n        context_info["social_gate_reason"] = gate_reason\n        context_info["social_gate_angle"] = gate_angle\n\n        # 模型认为 wick 真的有想法：可以主动说，但仍然保留一点克制。\n        if action == "reply" and confidence >= 0.62:\n            if silence >= 1 or random.random() < min(0.85, 0.35 + confidence * 0.55):\n                self.group_silence_count[chat_id] = 0\n                context_info["reply_relevance"] = max(score, 70)\n                context_info["reply_relevance_reason"] = f"社交判断：{gate_reason}"\n                return True, f"wick 有自己的想法：{gate_reason}"\n\n        # 可以说但不急：进候选队列，等一两句再合并。\n        if action in {"reply", "candidate"} and confidence >= 0.45:\n            self.group_silence_count[chat_id] = silence + 1\n            context_info["reply_relevance"] = max(score, 50)\n            context_info["reply_relevance_reason"] = f"候选想法：{gate_reason}"\n            return False, f"wick 有点想法但先观察：{gate_reason}"\n\n        self.group_silence_count[chat_id] = min(silence + 1, self.group_force_after_silence + 3)\n        return False, f"只观察：{gate_reason or reason}"\n'
NEW_ADD_BATCH = '\n    def _add_group_message_to_batch(\n        self,\n        chat_id: str,\n        sender_id: str,\n        text: str,\n        context_info: dict[str, Any],\n    ) -> tuple[bool, str]:\n        """把“模型判断有想法”的消息加入候选队列。\n\n        不再靠固定兴趣词；是否候选由 _social_gate_decide_via_api 决定。\n        """\n        score = int(context_info.get("reply_relevance", 0) or 0)\n        action = str(context_info.get("social_action", "") or "")\n        confidence = float(context_info.get("social_confidence", 0.0) or 0.0)\n        reason = str(context_info.get("reply_relevance_reason", "") or context_info.get("social_gate_reason", "") or "")\n        image_refs = list(context_info.get("image_refs", []))\n\n        if score < 45 and not (action in {"reply", "candidate"} and confidence >= 0.45):\n            return False, ""\n\n        now = datetime.now()\n        batch = self.pending_group_batches.get(chat_id)\n        if not batch:\n            batch = {\n                "due_at": now + timedelta(seconds=self.group_batch_max_wait_sec),\n                "messages": [],\n                "context_info": dict(context_info),\n            }\n            self.pending_group_batches[chat_id] = batch\n\n        sender_name = context_info.get("sender_name", "") or sender_id\n        current = {\n            "sender_id": sender_id,\n            "sender_name": sender_name,\n            "text": text,\n            "image_refs": image_refs,\n            "reply_relevance": max(score, 50 if action in {"reply", "candidate"} else score),\n            "reply_relevance_reason": reason,\n            "social_action": action,\n            "social_confidence": confidence,\n            "social_gate_angle": str(context_info.get("social_gate_angle", "") or ""),\n        }\n\n        messages = batch.setdefault("messages", [])\n        if not messages or not (\n            str(messages[-1].get("sender_id", "")) == sender_id\n            and str(messages[-1].get("text", "")) == text\n        ):\n            messages.append(current)\n\n        messages[:] = messages[-6:]\n        batch["context_info"] = dict(context_info)\n        batch["context_info"]["batch_messages"] = list(messages)\n\n        strong = [\n            m for m in messages\n            if int(m.get("reply_relevance", 0) or 0) >= 70\n            or (m.get("social_action") == "reply" and float(m.get("social_confidence", 0.0) or 0.0) >= 0.62)\n        ]\n        candidates = [\n            m for m in messages\n            if int(m.get("reply_relevance", 0) or 0) >= 45\n            or m.get("social_action") in {"reply", "candidate"}\n        ]\n\n        if strong and len(messages) >= 2:\n            combined = self._build_group_batch_text(messages)\n            self.pending_group_batches.pop(chat_id, None)\n            context_info["batch_messages"] = list(messages)\n            return True, combined\n\n        if len(candidates) >= 2:\n            combined = self._build_group_batch_text(messages)\n            self.pending_group_batches.pop(chat_id, None)\n            context_info["batch_messages"] = list(messages)\n            return True, combined\n\n        return False, ""\n'
NEW_BATCH = '\n    def _build_group_batch_text(self, messages: list[dict[str, Any]]) -> str:\n        """把候选群消息合成一次给模型看的输入。"""\n        lines = [\n            "下面是群里刚刚连续聊的几句话。",\n            "你是 wick，一个像真人一样旁听群聊的猫娘网友。",\n            "你的爱好、偏好、雷点、好奇心，不由代码关键词决定，而是从你的人设和最近聊天里自然推断。",\n            "如果这些话题碰到了你的在意点，你可以有自己的小想法；如果没有，就不要硬说。",\n            "回复策略：",\n            "1. 只在你真的有想法、好奇、吃味、吐槽欲，或者别人明显在找你时说话。",\n            "2. 不要逐条回复，不要总结群聊，不要解释程序机制。",\n            "3. 如果只是别人互相聊天、@别人、纯表情、纯图片，宁可不说。",\n            "4. 回复短一点，像 QQ 群友自然冒泡。",\n            "",\n            "候选片段：",\n        ]\n\n        for item in messages[-6:]:\n            name = str(item.get("sender_name", "") or item.get("sender_id", "") or "未知")\n            uid = str(item.get("sender_id", "") or "未知")\n            msg_text = str(item.get("text", "") or "").strip()\n            image_refs = item.get("image_refs", []) or []\n            relevance = int(item.get("reply_relevance", 0) or 0)\n            reason = str(item.get("reply_relevance_reason", "") or "")\n            action = str(item.get("social_action", "") or "")\n            confidence = item.get("social_confidence", "")\n            angle = str(item.get("social_gate_angle", "") or "")\n            if image_refs:\n                msg_text += f" [附带{len(image_refs)}张图片]"\n            extra = f"｜社交判断={action}/{confidence}｜角度={angle}" if action else ""\n            lines.append(f"- {name}(ID={uid})：{msg_text} ｜相关度={relevance}｜{reason}{extra}")\n\n        lines.append("")\n        lines.append("现在请根据你的人设自行判断要不要接话；要说就说一两句自己的想法，不要像执行规则。")\n        return "\\n".join(lines)\n'


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


def insert_before(src: str, before_method: str, block: str) -> str:
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
    raise RuntimeError(f"block 里找不到 {method_name}")


def ensure_helpers(src: str) -> str:
    helper_names = [
        "_build_wick_self_profile_text",
        "_strip_cq_for_social_gate",
        "_is_obvious_non_speech_message",
        "_social_gate_decide_via_api",
    ]
    for name in helper_names:
        method_text = extract_one_method(DYNAMIC_HELPERS, name)
        if method_range(src, name) is not None:
            src = replace_method(src, name, method_text)
        else:
            target = "_should_reply_to_group_message" if method_range(src, "_should_reply_to_group_message") else "_handle_message"
            src = insert_before(src, target, method_text)
    return src


def patch_generate_prompt(src: str) -> str:
    if "self_profile_block = self._build_wick_self_profile_text(context_info)" not in src:
        src = src.replace(
            "        context_block = self._build_context_block(text, context_info)\n",
            "        context_block = self._build_context_block(text, context_info)\n"
            "        self_profile_block = self._build_wick_self_profile_text(context_info)\n",
            1,
        )

    marker = '        if context_block:\n            system_prompt += f"\\n\\n### 当前上下文\\n{context_block}"\n'
    insert = (
        '        if self_profile_block:\n'
        '            system_prompt += f"\\n\\n### wick 的自我倾向\\n{self_profile_block}"\n'
        '        if context_block:\n'
        '            system_prompt += f"\\n\\n### 当前上下文\\n{context_block}"\n'
    )
    if marker in src and "### wick 的自我倾向" not in src:
        src = src.replace(marker, insert, 1)

    # 清理之前重复叠加的硬提示句，保留基础系统 prompt，不强行大改函数。
    duplicated = (
        "你不是被动问答机器，可以有自己的小想法。"
        "当话题有趣、正在聊你的 OC/人设/bot/猫娘/设定/bug，或者你真的有想吐槽的点时，"
        "即使没人 @ 你，也可以像真人群友一样低频接一句。"
        "但如果只是别人互相聊天、@别人、纯表情、纯图片，尽量不要抢话。"
    )
    src = src.replace(duplicated, "")

    return src


def patch_handle_threshold(src: str) -> str:
    # 如果人类社交判断给了 candidate/reply，就算 score 低也允许进入候选队列。
    old = (
        '                if score < 45 and not context_info.get("wick_has_own_opinion"):\n'
        '                    return ToolResult(True, reply_reason + " 已记录为背景，不进入合并回复队列。")'
    )
    new = (
        '                if score < 45 and context_info.get("social_action") not in {"reply", "candidate"}:\n'
        '                    return ToolResult(True, reply_reason + " 已记录为背景，不进入合并回复队列。")'
    )
    if old in src:
        src = src.replace(old, new, 1)

    old2 = (
        '                if score < 45:\n'
        '                    return ToolResult(True, reply_reason + " 已记录为背景，不进入合并回复队列。")'
    )
    if old2 in src:
        src = src.replace(old2, new, 1)

    return src


def patch_defaults(src: str) -> str:
    # gate 已经交给模型判断，这里只保留一个很低的兜底随机性。
    src = src.replace("self.group_reply_probability = 0.03", "self.group_reply_probability = 0.05")
    src = src.replace("self.group_reply_probability = 0.04", "self.group_reply_probability = 0.05")
    src = src.replace("self.group_reply_probability = 0.06", "self.group_reply_probability = 0.05")
    return src


def main() -> None:
    if not TARGET.exists():
        raise SystemExit(f"找不到文件：{TARGET}")

    src = TARGET.read_text(encoding="utf-8")
    backup = TARGET.with_suffix(".py.bak_dynamic_personality_gate")
    backup.write_text(src, encoding="utf-8")

    src = patch_defaults(src)
    src = ensure_helpers(src)
    src = replace_method(src, "_should_reply_to_group_message", NEW_SHOULD)
    src = replace_method(src, "_add_group_message_to_batch", NEW_ADD_BATCH)
    src = replace_method(src, "_build_group_batch_text", NEW_BATCH)
    src = patch_handle_threshold(src)
    src = patch_generate_prompt(src)

    compile(src, str(TARGET), "exec")
    TARGET.write_text(src, encoding="utf-8")

    print("✅ 已改成动态人格社交判断")
    print("不再用固定兴趣词决定主动发言；会让模型从 custom_prompt 和最近聊天里判断 wick 是否有自己的想法。")
    print("注意：非 @ 的普通群消息会多一次小模型/同模型 gate 请求，换取更像真人的主动判断。")
    print(f"备份文件：{backup}")
    print("下一步：")
    print("  python -m py_compile .\\src\\clawmini\\tools\\qq_auto_reply.py")
    print("  python app.py")


if __name__ == "__main__":
    main()
