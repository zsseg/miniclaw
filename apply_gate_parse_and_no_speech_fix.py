#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import ast
from pathlib import Path


PROJECT_ROOT = Path.cwd()
TARGET = PROJECT_ROOT / "src" / "clawmini" / "tools" / "qq_auto_reply.py"

HELPERS = '\n    def _extract_persona_terms_from_prompt(self, limit: int = 80) -> list[str]:\n        """从 custom_prompt 里动态抽取人设词，不把爱好写死在代码里。"""\n        prompt = str(getattr(self, "custom_prompt", "") or "")\n        if not prompt:\n            return []\n\n        cleaned = re.sub(r"\\[CQ:[^\\]]+\\]", " ", prompt)\n        chunks = re.findall(r"[\\u4e00-\\u9fffA-Za-z0-9_]{2,12}", cleaned)\n\n        stop = {\n            "现在", "一个", "这个", "那个", "如果", "不要", "可以", "但是", "因为", "所以",\n            "回复", "输出", "用户", "群聊", "私聊", "内容", "时候", "自己", "别人", "消息",\n            "自然", "一点", "控制", "普通", "需要", "应该", "进行", "根据", "什么", "怎么",\n            "没有", "不是", "聊天", "说话", "语气", "文字", "markdown", "Markdown", "QQ", "qq",\n        }\n\n        terms: list[str] = []\n\n        def add(term: str) -> None:\n            term = term.strip()\n            if len(term) < 2 or term in stop:\n                return\n            if term.lower() in {t.lower() for t in terms}:\n                return\n            terms.append(term)\n\n        for chunk in chunks:\n            if chunk in stop:\n                continue\n            if re.fullmatch(r"[A-Za-z0-9_]{2,20}", chunk):\n                add(chunk)\n                continue\n            if 2 <= len(chunk) <= 4:\n                add(chunk)\n            else:\n                for n in (4, 3, 2):\n                    for i in range(0, max(0, len(chunk) - n + 1)):\n                        add(chunk[i:i+n])\n                        if len(terms) >= limit:\n                            return terms\n            if len(terms) >= limit:\n                return terms\n        return terms\n\n    def _current_text_matches_persona_prompt(self, text: str) -> tuple[bool, str]:\n        """当前消息是否碰到了 custom_prompt 里的人设词。"""\n        clean = str(text or "")\n        clean = re.sub(r"\\[CQ:[^\\]]+\\]", " ", clean)\n        terms = self._extract_persona_terms_from_prompt()\n        hits: list[str] = []\n        for term in terms:\n            if term and term in clean:\n                hits.append(term)\n                if len(hits) >= 5:\n                    break\n        if hits:\n            return True, "、".join(hits)\n        return False, ""\n\n    def _dynamic_persona_fallback_decision(\n        self,\n        text: str,\n        context_info: dict[str, Any] | None = None,\n        reason: str = "",\n    ) -> dict[str, Any]:\n        """gate 失败时兜底，避免 gate 一失败就变哑巴。"""\n        context_info = context_info or {}\n        raw = str(text or "")\n\n        try:\n            clean = self._strip_cq_for_social_gate(raw)\n        except Exception:\n            clean = re.sub(r"\\[CQ:[^\\]]+\\]", " ", raw).strip()\n\n        if not clean:\n            return {"action": "observe", "confidence": 0.0, "reason": reason or "低信息消息", "angle": ""}\n\n        try:\n            if self._is_at_other_user_message(raw) and not self._text_explicitly_about_self_bot(raw):\n                return {"action": "observe", "confidence": 0.0, "reason": "@的是别人", "angle": ""}\n        except Exception:\n            pass\n\n        persona_hit, persona_terms = self._current_text_matches_persona_prompt(clean)\n        pronoun_like = any(x in clean for x in ("他", "它", "她", "这个", "这只", "那只", "wick", "猫娘", "机器人", "bot"))\n\n        if persona_hit and pronoun_like:\n            return {\n                "action": "reply",\n                "confidence": 0.78,\n                "reason": f"当前消息命中了人设词：{persona_terms}",\n                "angle": "用 wick 自己的角色口吻对这个评价做出反应，表现一点自己的态度",\n            }\n\n        if persona_hit:\n            return {\n                "action": "candidate",\n                "confidence": 0.56,\n                "reason": f"话题碰到了 wick 人设：{persona_terms}",\n                "angle": "根据人设自然接一句自己的看法",\n            }\n\n        chat_id = str(context_info.get("chat_id", "") or "")\n        sender_id = str(context_info.get("sender_id", "") or "")\n        recent_texts: list[str] = []\n        same_sender_count = 0\n\n        try:\n            for item in self.recent_messages.get(chat_id, [])[-12:]:\n                if not isinstance(item, dict):\n                    continue\n                item_sender = str(item.get("sender_id", "") or "")\n                item_text = str(item.get("text", "") or "")\n                item_reply = str(item.get("reply", "") or "")\n                if item_text:\n                    recent_texts.append(item_text)\n                if item_reply:\n                    recent_texts.append(item_reply)\n                if sender_id and item_sender == sender_id:\n                    same_sender_count += 1\n        except Exception:\n            pass\n\n        try:\n            batch = self.pending_group_batches.get(chat_id)\n            if isinstance(batch, dict):\n                for item in batch.get("messages", [])[-8:]:\n                    if not isinstance(item, dict):\n                        continue\n                    item_sender = str(item.get("sender_id", "") or "")\n                    item_text = str(item.get("text", "") or "")\n                    if item_text:\n                        recent_texts.append(item_text)\n                    if sender_id and item_sender == sender_id:\n                        same_sender_count += 1\n        except Exception:\n            pass\n\n        recent_blob = "\\n".join(recent_texts[-12:]).lower()\n        meta_signals = [\n            "上下文", "候选", "回复", "判断", "自言自语", "哑巴", "说话",\n            "好不好使", "不说话", "为什么", "怎么", "代码", "出锅", "bug",\n            "bot", "机器人", "wick", "redamancy", "猫娘",\n        ]\n        current_meta = any(s in clean.lower() for s in meta_signals)\n        recent_meta = any(s in recent_blob for s in meta_signals)\n\n        if current_meta or (same_sender_count >= 1 and recent_meta and any(x in clean for x in ("他", "它", "这个", "不对", "对", "不是"))):\n            return {\n                "action": "reply",\n                "confidence": 0.66,\n                "reason": "当前发言在讨论 wick/回复效果/对话状态",\n                "angle": "用角色口吻回应，不要继续装作没听见",\n            }\n\n        if same_sender_count >= 2 and len(clean) >= 2:\n            return {\n                "action": "candidate",\n                "confidence": 0.42,\n                "reason": "同一用户连续发言，可能在延续上文",\n                "angle": "等更多上下文再接",\n            }\n\n        return {"action": "observe", "confidence": 0.0, "reason": reason or "没有明显开口点", "angle": ""}\n\n    def _parse_social_gate_response(self, content: str) -> dict[str, Any] | None:\n        """宽松解析 gate 输出，避免 JSON 稍微坏一点就报错。"""\n        text = str(content or "").strip()\n        if not text:\n            return None\n\n        # 先尝试标准 JSON / JSON 子串\n        try:\n            return json.loads(text)\n        except Exception:\n            pass\n\n        match = re.search(r"\\{[\\s\\S]*\\}", text)\n        if match:\n            candidate = match.group(0)\n            try:\n                return json.loads(candidate)\n            except Exception:\n                text = candidate\n\n        # 再宽松解析半截 JSON，例如 {"action":"reply","reason":"...\n        action = ""\n        m = re.search(r\'"?action"?\\s*[:=]\\s*"?\\s*(reply|candidate|observe)\', text, re.I)\n        if m:\n            action = m.group(1).lower()\n        else:\n            lowered = text.lower()\n            if "reply" in lowered:\n                action = "reply"\n            elif "candidate" in lowered:\n                action = "candidate"\n            elif "observe" in lowered:\n                action = "observe"\n\n        if not action:\n            return None\n\n        confidence = 0.5\n        m = re.search(r\'"?confidence"?\\s*[:=]\\s*([01](?:\\.\\d+)?)\', text, re.I)\n        if m:\n            try:\n                confidence = float(m.group(1))\n            except Exception:\n                confidence = 0.5\n\n        reason = ""\n        m = re.search(r\'"?reason"?\\s*[:=]\\s*"([^"\\n\\r]{0,120})\', text, re.I)\n        if m:\n            reason = m.group(1)\n\n        angle = ""\n        m = re.search(r\'"?angle"?\\s*[:=]\\s*"([^"\\n\\r]{0,160})\', text, re.I)\n        if m:\n            angle = m.group(1)\n\n        return {\n            "action": action,\n            "confidence": max(0.0, min(1.0, confidence)),\n            "reason": reason or "宽松解析 gate 输出",\n            "angle": angle,\n        }\n\n    def _looks_like_no_speech_reply(self, reply: str) -> bool:\n        """识别不应该真的发出去的“内心戏/不回复占位”。"""\n        text = str(reply or "").strip()\n        if not text:\n            return True\n\n        compact = re.sub(r"\\s+", "", text)\n        compact = compact.strip("()（）[]【】")\n\n        hard_no_speech = {\n            "不回复",\n            "不说话",\n            "保持沉默",\n            "默默看着",\n            "不插话",\n            "只观察",\n            "等待更多上下文",\n            "继续观察",\n            "先不回复",\n            "先不说话",\n        }\n\n        if compact in hard_no_speech:\n            return True\n\n        # 短括号旁白，例如（不回复）、（默默看着，不插话）\n        if len(compact) <= 18 and any(key in compact for key in hard_no_speech):\n            return True\n\n        # “我不回复/不插话”这种如果是完整自然句可以保留；只过滤纯占位。\n        if text.startswith(("（", "(", "【", "[")) and len(compact) <= 24:\n            if any(key in compact for key in hard_no_speech):\n                return True\n\n        return False\n'
SOCIAL_GATE = '\n    def _social_gate_decide_via_api(\n        self,\n        text: str,\n        context_info: dict[str, Any] | None = None,\n    ) -> dict[str, Any]:\n        """让模型判断 wick 要不要主动说话。\n\n        修复点：\n        - gate 不显式传 thinking，降低空 content；\n        - max_tokens 提高；\n        - JSON 解析失败时宽松解析；\n        - 仍失败则走动态人设兜底；\n        - observe 但兜底明显认为在聊 wick 时，采用兜底。\n        """\n        context_info = context_info or {}\n\n        provider = self.reply_api_provider.strip().lower()\n        api_key = self.reply_api_key.strip()\n        if provider not in {"openai", "deepseek", "qwen"} or not api_key:\n            return self._dynamic_persona_fallback_decision(text, context_info, "没有可用 API 做社交判断")\n\n        raw_text = str(text or "")\n\n        try:\n            if self._is_obvious_non_speech_message(raw_text, context_info):\n                fallback = self._dynamic_persona_fallback_decision(raw_text, context_info, "明显低信息消息")\n                if fallback.get("action") in {"reply", "candidate"}:\n                    return fallback\n                return {"action": "observe", "confidence": 0.0, "reason": "明显不是该主动说话的消息", "angle": ""}\n        except Exception:\n            pass\n\n        if self.reply_api_model.strip():\n            model_name = self.reply_api_model.strip()\n        elif provider == "deepseek":\n            model_name = "deepseek-v4-pro"\n        elif provider == "qwen":\n            model_name = "qwen-plus"\n        else:\n            model_name = "gpt-4o-mini"\n\n        base_url = self.reply_api_base_url.strip()\n        if provider == "deepseek" and not base_url:\n            base_url = "https://api.deepseek.com"\n        if provider == "deepseek" and base_url.rstrip("/").endswith("/v1"):\n            base_url = base_url.rstrip("/")[:-3].rstrip("/")\n        if provider == "openai" and not base_url:\n            base_url = "https://api.openai.com/v1"\n        if provider == "qwen" and not base_url:\n            base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"\n\n        endpoint = base_url.rstrip("/") + "/chat/completions"\n\n        try:\n            self_profile = self._build_wick_self_profile_text(context_info)\n        except Exception:\n            self_profile = str(getattr(self, "custom_prompt", "") or "")\n\n        try:\n            context_block = self._build_context_block(text, context_info)\n        except Exception:\n            context_block = ""\n\n        gate_prompt = (\n            "你在帮 QQ 群里的猫娘 wick 判断：现在要不要开口。\\n"\n            "不要靠固定关键词。请根据 wick 的人设、最近聊天、当前话题，判断她是否真的有自己的想法。\\n"\n            "如果当前消息是在评价 wick 的人设、性格、状态、说话方式，即使没有 @，也通常应该 reply。\\n"\n            "如果只是别人互相聊天、@别人、纯表情、纯图片、或者 wick 说了也没新东西，就 observe。\\n"\n            "reply = 现在就说；candidate = 可以等几句合并再说；observe = 只看不说。\\n"\n            "只输出严格 JSON，不要 Markdown，不要前后解释，不要代码块。\\n"\n            \'{"action":"reply|candidate|observe","confidence":0.0,"reason":"短原因","angle":"如果开口，从什么角度说"}\'\n        )\n\n        user_gate = (\n            f"wick 自我倾向：\\n{self_profile[:1800]}\\n\\n"\n            f"当前上下文：\\n{context_block[:2600]}\\n\\n"\n            f"当前消息：{raw_text[:600]}"\n        )\n\n        payload: dict[str, Any] = {\n            "model": model_name,\n            "messages": [\n                {"role": "system", "content": gate_prompt},\n                {"role": "user", "content": user_gate},\n            ],\n            "max_tokens": 700,\n        }\n\n        # gate 不传 thinking/reasoning_effort。\n        if provider != "deepseek":\n            payload["temperature"] = 0.15\n\n        req = urllib.request.Request(\n            endpoint,\n            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),\n            headers={\n                "Authorization": f"Bearer {api_key}",\n                "Content-Type": "application/json",\n            },\n            method="POST",\n        )\n\n        try:\n            with urllib.request.urlopen(req, timeout=25) as resp:\n                body = json.loads(resp.read().decode("utf-8"))\n            msg = body.get("choices", [{}])[0].get("message", {})\n            content = str(msg.get("content", "") or "").strip()\n\n            if not content:\n                return self._dynamic_persona_fallback_decision(text, context_info, "gate返回空内容")\n\n            data = self._parse_social_gate_response(content)\n            if not isinstance(data, dict):\n                return self._dynamic_persona_fallback_decision(text, context_info, "gate输出无法解析")\n\n            action = str(data.get("action", "observe")).strip().lower()\n            if action not in {"reply", "candidate", "observe"}:\n                action = "observe"\n\n            try:\n                confidence = float(data.get("confidence", 0.0))\n            except Exception:\n                confidence = 0.0\n            confidence = max(0.0, min(1.0, confidence))\n\n            if action == "observe":\n                fallback = self._dynamic_persona_fallback_decision(text, context_info, str(data.get("reason", "")))\n                if fallback.get("action") == "reply":\n                    return fallback\n\n            return {\n                "action": action,\n                "confidence": confidence,\n                "reason": str(data.get("reason", ""))[:120],\n                "angle": str(data.get("angle", ""))[:180],\n            }\n        except Exception as exc:\n            return self._dynamic_persona_fallback_decision(text, context_info, f"gate失败：{exc}")\n'
SHOULD_PATCH = '\n    def _should_reply_to_group_message(\n        self,\n        chat_id: str,\n        text: str,\n        mentioned: bool,\n        image_refs: list[str],\n        context_info: dict[str, Any] | None = None,\n    ) -> tuple[bool, str]:\n        """像真人一样决定要不要开口。"""\n        context_info = context_info or {}\n\n        try:\n            score, reason = self._score_group_message_relevance(\n                text=text,\n                mentioned=mentioned,\n                image_refs=image_refs,\n                context_info=context_info,\n            )\n        except Exception:\n            score, reason = (0, "未能打分")\n\n        context_info["reply_relevance"] = score\n        context_info["reply_relevance_reason"] = reason\n\n        if mentioned or score >= 90:\n            self.group_silence_count[chat_id] = 0\n            return True, f"{reason} 立即回复。"\n\n        try:\n            if self._is_at_other_user_message(text) and not self._text_explicitly_about_self_bot(text):\n                self.group_silence_count[chat_id] = self.group_silence_count.get(chat_id, 0) + 1\n                context_info["social_action"] = "observe"\n                context_info["social_gate_reason"] = "@的是别人"\n                return False, "@的是别人，不抢话。"\n        except Exception:\n            pass\n\n        silence = self.group_silence_count.get(chat_id, 0)\n        decision = self._social_gate_decide_via_api(text, context_info)\n        action = str(decision.get("action", "observe"))\n        confidence = float(decision.get("confidence", 0.0) or 0.0)\n        gate_reason = str(decision.get("reason", "") or "")\n        gate_angle = str(decision.get("angle", "") or "")\n\n        context_info["social_action"] = action\n        context_info["social_confidence"] = confidence\n        context_info["social_gate_reason"] = gate_reason\n        context_info["social_gate_angle"] = gate_angle\n\n        if action == "reply" and confidence >= 0.50:\n            if silence >= 1 or random.random() < min(0.90, 0.45 + confidence * 0.50):\n                self.group_silence_count[chat_id] = 0\n                context_info["reply_relevance"] = max(score, 70)\n                context_info["reply_relevance_reason"] = f"社交判断：{gate_reason}"\n                return True, f"wick 有自己的想法：{gate_reason}"\n\n        if action in {"reply", "candidate"} and confidence >= 0.35:\n            self.group_silence_count[chat_id] = silence + 1\n            context_info["reply_relevance"] = max(score, 50)\n            context_info["reply_relevance_reason"] = f"候选想法：{gate_reason}"\n            return False, f"wick 有点想法但先观察：{gate_reason}"\n\n        self.group_silence_count[chat_id] = min(silence + 1, self.group_force_after_silence + 3)\n        return False, f"只观察：{gate_reason or reason}"\n'


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
    names = [
        "_extract_persona_terms_from_prompt",
        "_current_text_matches_persona_prompt",
        "_dynamic_persona_fallback_decision",
        "_parse_social_gate_response",
        "_looks_like_no_speech_reply",
    ]
    for name in names:
        method_text = extract_one_method(HELPERS, name)
        if method_range(src, name) is not None:
            src = replace_method(src, name, method_text)
        else:
            target = "_social_gate_decide_via_api" if method_range(src, "_social_gate_decide_via_api") else "_should_reply_to_group_message"
            src = insert_before(src, target, method_text)
    return src


def patch_handle_threshold(src: str) -> str:
    patterns = [
        (
            '                if score < 45 and not context_info.get("wick_has_own_opinion"):\n'
            '                    return ToolResult(True, reply_reason + " 已记录为背景，不进入合并回复队列。")',
            '                if score < 45 and context_info.get("social_action") not in {"reply", "candidate"}:\n'
            '                    return ToolResult(True, reply_reason + " 已记录为背景，不进入合并回复队列。")',
        ),
        (
            '                if score < 45:\n'
            '                    return ToolResult(True, reply_reason + " 已记录为背景，不进入合并回复队列。")',
            '                if score < 45 and context_info.get("social_action") not in {"reply", "candidate"}:\n'
            '                    return ToolResult(True, reply_reason + " 已记录为背景，不进入合并回复队列。")',
        ),
    ]
    for old, new in patterns:
        if old in src:
            src = src.replace(old, new, 1)
    return src


def patch_at_self_detection(src: str) -> str:
    if "补充判断：NapCat 有时 mentioned=false" in src:
        return src

    old = '            mentioned = bool(arguments.get("mentioned", False))\n'
    new = (
        '            mentioned = bool(arguments.get("mentioned", False))\n'
        '            # 补充判断：NapCat 有时 mentioned=false，但 text 里实际带了 [CQ:at,qq=机器人QQ]\n'
        '            try:\n'
        '                if not mentioned and str(self.self_user_id) and f"[CQ:at,qq={self.self_user_id}" in raw_text:\n'
        '                    mentioned = True\n'
        '            except Exception:\n'
        '                pass\n'
    )
    if old in src:
        src = src.replace(old, new, 1)
    return src


def patch_no_speech_filter(src: str) -> str:
    if "过滤模型产出的不回复占位" in src:
        return src

    old = '        reply_parts = self._build_reply_parts(text, context_info=context_info)\n        if not reply_parts:\n            return ToolResult(False, "未生成可发送的回复内容。")'
    new = (
        '        reply_parts = self._build_reply_parts(text, context_info=context_info)\n'
        '        # 过滤模型产出的不回复占位，例如（不回复）、（默默看着，不插话）\n'
        '        reply_parts = [part for part in reply_parts if not self._looks_like_no_speech_reply(part)]\n'
        '        if not reply_parts:\n'
        '            return ToolResult(True, "模型选择不回复，已拦截不回复占位。")'
    )
    if old in src:
        src = src.replace(old, new, 1)
    else:
        print("⚠️ 没找到 reply_parts 过滤插入点，已跳过不回复占位过滤。")
    return src


def patch_generation_prompt(src: str) -> str:
    addition = (
        "如果你真的不想回复，就不要输出“（不回复）”“（默默看着）”“不插话”这类占位文本；"
        "一旦生成回复，就必须是能直接发到 QQ 里的自然聊天内容，不要写内心戏旁白。"
    )
    if addition in src:
        return src

    marker = "不要输出 Markdown、标题、编号、解释性前言。"
    if marker in src:
        src = src.replace(marker, marker + addition, 1)
    return src


def main() -> None:
    if not TARGET.exists():
        raise SystemExit(f"找不到文件：{TARGET}")

    src = TARGET.read_text(encoding="utf-8")
    backup = TARGET.with_suffix(".py.bak_gate_parse_and_no_speech")
    backup.write_text(src, encoding="utf-8")

    src = ensure_helpers(src)
    if method_range(src, "_social_gate_decide_via_api") is None:
        src = insert_before(src, "_should_reply_to_group_message", SOCIAL_GATE)
    else:
        src = replace_method(src, "_social_gate_decide_via_api", SOCIAL_GATE)

    src = replace_method(src, "_should_reply_to_group_message", SHOULD_PATCH)
    src = patch_handle_threshold(src)
    src = patch_at_self_detection(src)
    src = patch_no_speech_filter(src)
    src = patch_generation_prompt(src)

    compile(src, str(TARGET), "exec")
    TARGET.write_text(src, encoding="utf-8")

    print("✅ 已修复 gate 解析失败和不回复占位")
    print("修复内容：gate JSON 宽松解析、失败动态兜底、@自己补充识别、拦截（不回复）/（默默看着，不插话）。")
    print(f"备份文件：{backup}")
    print("下一步：")
    print("  python -m py_compile .\\src\\clawmini\\tools\\qq_auto_reply.py")
    print("  python app.py")


if __name__ == "__main__":
    main()
