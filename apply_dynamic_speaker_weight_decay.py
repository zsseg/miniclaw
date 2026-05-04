#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import ast
from pathlib import Path


PROJECT_ROOT = Path.cwd()
TARGET = PROJECT_ROOT / "src" / "clawmini" / "tools" / "qq_auto_reply.py"

HELPERS = '\n    def _persona_runtime_profile_for_model(self) -> str:\n        """运行时人设资料。\n\n        只读取用户当前配置的 custom_prompt，不在代码里写死名字、人设、兴趣点。\n        """\n        custom = str(getattr(self, "custom_prompt", "") or "").strip()\n        if not custom:\n            return (\n                "当前没有额外人设配置。你只能作为当前账号的普通群友说话，"\n                "不要自行发明固定名字、固定爱好或固定人设。"\n            )\n        return (\n            "以下是当前用户配置的人设原文。具体名字、性格、兴趣、雷点、口癖都只能从这里和最近聊天中推断，"\n            "不要使用代码里的旧默认人设，也不要把任何示例词当固定设定。\\n"\n            f"{custom[:1800]}"\n        )\n\n    def _speaker_label_for_model(self, sender_id: str, sender_name: str = "", label_map: dict[str, str] | None = None) -> str:\n        """给模型看的发言者标签。"""\n        sid = str(sender_id or "").strip()\n        name = str(sender_name or "").strip()\n\n        if sid in {"SELF", "BOT", "ME"}:\n            return "SELF(当前机器人账号)"\n\n        if label_map is not None:\n            key = sid or name or "unknown"\n            if key not in label_map:\n                label_map[key] = f"S{len(label_map) + 1}"\n            prefix = label_map[key]\n        else:\n            prefix = "S?"\n\n        if name and sid:\n            return f"{prefix}({name}, QQ={sid})"\n        if sid:\n            return f"{prefix}(QQ={sid})"\n        if name:\n            return f"{prefix}({name})"\n        return f"{prefix}(未知群友)"\n\n    def _normalize_context_text_for_model(self, text: str) -> str:\n        t = str(text or "").strip()\n        t = re.sub(r"\\[CQ:image[^\\]]*\\]", "[图片]", t)\n        t = re.sub(r"\\[CQ:face[^\\]]*\\]", "[表情]", t)\n        t = re.sub(r"\\[CQ:forward[^\\]]*\\]", "[合并转发]", t)\n        t = re.sub(r"\\[CQ:at,qq=([0-9]+)[^\\]]*\\]", r"[@\\1]", t)\n        t = re.sub(r"\\[CQ:reply[^\\]]*\\]", "[回复某条消息]", t)\n        t = re.sub(r"\\s+", " ", t).strip()\n        return t[:180]\n\n    def _candidate_timestamp(self, item: dict[str, Any], default: datetime | None = None) -> datetime:\n        default = default or datetime.now()\n        raw = item.get("created_at") or item.get("time") or item.get("timestamp")\n        if isinstance(raw, datetime):\n            return raw\n        if isinstance(raw, (int, float)):\n            try:\n                if raw > 10_000_000:\n                    return datetime.fromtimestamp(float(raw))\n            except Exception:\n                pass\n        if isinstance(raw, str) and raw.strip():\n            try:\n                return datetime.fromisoformat(raw.strip())\n            except Exception:\n                pass\n        return default\n\n    def _candidate_base_weight(self, item: dict[str, Any]) -> float:\n        """候选基础权重：由相关度、gate 置信度和显式性组成。"""\n        try:\n            relevance = float(item.get("reply_relevance", 0) or 0) / 100.0\n        except Exception:\n            relevance = 0.0\n\n        try:\n            confidence = float(item.get("social_confidence", 0.0) or 0.0)\n        except Exception:\n            confidence = 0.0\n\n        action = str(item.get("social_action", "") or "")\n        weight = max(relevance, confidence)\n\n        if action == "reply":\n            weight += 0.16\n        elif action == "candidate":\n            weight += 0.06\n\n        if item.get("mentioned") or item.get("explicit_self"):\n            weight += 0.28\n\n        if item.get("recent_image_context") and not item.get("explicit_image_question"):\n            weight *= 0.55\n\n        text = str(item.get("text", "") or "")\n        if "[CQ:face" in text and not re.sub(r"\\[CQ:[^\\]]+\\]", "", text).strip():\n            weight *= 0.35\n        if "[CQ:image" in text and not re.sub(r"\\[CQ:[^\\]]+\\]", "", text).strip():\n            weight *= 0.25\n\n        return max(0.0, min(weight, 1.35))\n\n    def _candidate_decayed_weight(self, item: dict[str, Any], now: datetime | None = None) -> float:\n        """候选权重随时间衰减，旧候选逐渐变背景，而不是直接硬压缩。"""\n        now = now or datetime.now()\n        base = float(item.get("candidate_weight", 0.0) or 0.0)\n        if base <= 0:\n            base = self._candidate_base_weight(item)\n\n        created_at = self._candidate_timestamp(item, default=now)\n        try:\n            age_sec = max(0.0, (now - created_at).total_seconds())\n        except Exception:\n            age_sec = 0.0\n\n        try:\n            half_life = float(os.getenv("QQ_CANDIDATE_HALF_LIFE_SEC", "22"))\n        except Exception:\n            half_life = 22.0\n        half_life = max(8.0, min(half_life, 90.0))\n\n        decay = 0.5 ** (age_sec / half_life)\n        weight = base * decay\n\n        if age_sec > 70 and not item.get("mentioned") and not item.get("explicit_self"):\n            weight *= 0.25\n\n        return max(0.0, min(weight, 1.5))\n\n    def _candidate_should_keep_as_background(self, item: dict[str, Any], now: datetime | None = None) -> bool:\n        now = now or datetime.now()\n        created_at = self._candidate_timestamp(item, default=now)\n        try:\n            age_sec = max(0.0, (now - created_at).total_seconds())\n        except Exception:\n            age_sec = 0.0\n        return age_sec <= 150\n\n    def _build_weighted_speaker_context(\n        self,\n        context_info: dict[str, Any] | None = None,\n        current_text: str = "",\n    ) -> str:\n        """构造动态发言者上下文，不绑定固定人设。"""\n        context_info = context_info or {}\n        chat_id = str(context_info.get("chat_id", "") or "")\n        current_sender_id = str(context_info.get("sender_id", "") or "")\n        current_sender_name = str(context_info.get("sender_name", "") or "")\n\n        label_map: dict[str, str] = {}\n        rows: list[dict[str, Any]] = []\n        now = datetime.now()\n\n        def add_row(kind: str, sender_id: str, sender_name: str, text: str, **extra: Any) -> None:\n            text = str(text or "").strip()\n            if not text:\n                return\n            rows.append(\n                {\n                    "kind": kind,\n                    "sender_id": str(sender_id or ""),\n                    "sender_name": str(sender_name or ""),\n                    "text": text,\n                    **extra,\n                }\n            )\n\n        try:\n            for item in self.recent_messages.get(chat_id, [])[-12:]:\n                if not isinstance(item, dict):\n                    continue\n                sid = str(item.get("sender_id", "") or item.get("speaker", "") or "")\n                sname = str(item.get("sender_name", "") or "")\n                text = str(item.get("text", "") or "").strip()\n                reply = str(item.get("reply", "") or "").strip()\n                if text:\n                    add_row("最近", sid, sname, text)\n                if reply:\n                    add_row("最近", "SELF", "SELF", reply)\n        except Exception:\n            pass\n\n        try:\n            batch_messages = context_info.get("batch_messages", [])\n            if isinstance(batch_messages, list):\n                for item in batch_messages[-12:]:\n                    if not isinstance(item, dict):\n                        continue\n                    add_row(\n                        "候选",\n                        str(item.get("sender_id", "") or ""),\n                        str(item.get("sender_name", "") or ""),\n                        str(item.get("text", "") or ""),\n                        weight=self._candidate_decayed_weight(item, now),\n                        base_weight=self._candidate_base_weight(item),\n                        reason=str(item.get("reply_relevance_reason", "") or item.get("social_gate_reason", "") or ""),\n                    )\n        except Exception:\n            pass\n\n        if current_text:\n            add_row("当前", current_sender_id, current_sender_name, current_text, weight=1.0)\n\n        deduped: list[dict[str, Any]] = []\n        seen: set[str] = set()\n        for row in rows:\n            key = f"{row.get(\'kind\')}|{row.get(\'sender_id\')}|{row.get(\'text\')}"\n            if key in seen:\n                continue\n            seen.add(key)\n            deduped.append(row)\n\n        lines = [\n            "### 当前人设来源",\n            self._persona_runtime_profile_for_model(),\n            "",\n            "### 发言者理解规则",\n            "SELF 是当前机器人账号；S1/S2/S3 是不同 QQ 号的群友。",\n            "先判断当前消息是谁说的，再判断它在回应谁。",\n            "不要把不同 S 编号的群友当成同一个人；不要把 A 的话接到 B 身上。",\n            "群聊里的“你/他/她/它/这个”要根据最近时间线推断指代，不能默认指 SELF。",\n            "第三方模型、软件、工具、平台名不自动等于 SELF，除非当前人设原文明确这么说。",\n            "如果不确定指代，优先少说或用不确定语气；不要自信编造。",\n            "",\n            "### 最近对话时间线",\n        ]\n\n        if not deduped:\n            lines.append("暂无有效上下文。")\n        else:\n            for row in deduped[-16:]:\n                sid = str(row.get("sender_id", ""))\n                sname = str(row.get("sender_name", ""))\n                speaker = self._speaker_label_for_model(sid, sname, label_map)\n                text = self._normalize_context_text_for_model(str(row.get("text", "")))\n                kind = str(row.get("kind", ""))\n                marker = " ← 当前消息" if kind == "当前" else ""\n                weight = row.get("weight", None)\n                if weight is not None:\n                    try:\n                        lines.append(f"- [{kind}] {speaker}: {text} ｜候选权重={float(weight):.2f}{marker}")\n                    except Exception:\n                        lines.append(f"- [{kind}] {speaker}: {text}{marker}")\n                else:\n                    lines.append(f"- [{kind}] {speaker}: {text}{marker}")\n\n        if current_sender_id:\n            lines.append("")\n            lines.append(\n                "当前发言者 = "\n                + self._speaker_label_for_model(current_sender_id, current_sender_name, label_map)\n            )\n\n        return "\\n".join(lines)\n'
NEW_ADD_BATCH = '\n    def _add_group_message_to_batch(\n        self,\n        chat_id: str,\n        sender_id: str,\n        text: str,\n        context_info: dict[str, Any],\n    ) -> tuple[bool, str]:\n        """把候选消息加入队列。\n\n        不再简单压缩成最近 N 条；每条候选带权重和时间戳，之后按半衰期自然衰减。\n        """\n        try:\n            if self._is_echo_of_recent_bot_reply(chat_id, text):\n                return False, ""\n        except Exception:\n            pass\n\n        score = int(context_info.get("reply_relevance", 0) or 0)\n        reason = str(context_info.get("reply_relevance_reason", "") or context_info.get("social_gate_reason", "") or "")\n        action = str(context_info.get("social_action", "") or "")\n        confidence = float(context_info.get("social_confidence", 0.0) or 0.0)\n        image_refs = list(context_info.get("image_refs", []))\n        mentioned = bool(context_info.get("mentioned") or context_info.get("explicit_self"))\n\n        if score < 45 and not (action in {"reply", "candidate"} and confidence >= 0.35) and not mentioned:\n            return False, ""\n\n        now = datetime.now()\n        batch = self.pending_group_batches.get(chat_id)\n        if not batch:\n            try:\n                wait_sec = int(getattr(self, "group_batch_max_wait_sec", 18) or 18)\n            except Exception:\n                wait_sec = 18\n            wait_sec = max(8, min(wait_sec, 16))\n            batch = {\n                "due_at": now + timedelta(seconds=wait_sec),\n                "messages": [],\n                "context_info": dict(context_info),\n            }\n            self.pending_group_batches[chat_id] = batch\n\n        sender_name = context_info.get("sender_name", "") or sender_id\n        current = {\n            "sender_id": sender_id,\n            "sender_name": sender_name,\n            "chat_id": chat_id,\n            "text": text,\n            "image_refs": image_refs,\n            "reply_relevance": max(score, 50 if action in {"reply", "candidate"} else score),\n            "reply_relevance_reason": reason,\n            "social_action": action,\n            "social_confidence": confidence,\n            "social_gate_angle": str(context_info.get("social_gate_angle", "") or ""),\n            "mentioned": mentioned,\n            "explicit_self": bool(context_info.get("explicit_self", False)),\n            "explicit_image_question": bool(context_info.get("explicit_image_question", False)),\n            "recent_image_context": bool(context_info.get("recent_image_context", False)),\n            "created_at": now.isoformat(timespec="seconds"),\n        }\n        current["candidate_weight"] = self._candidate_base_weight(current)\n\n        messages = batch.setdefault("messages", [])\n        if not messages or not (\n            str(messages[-1].get("sender_id", "")) == sender_id\n            and str(messages[-1].get("text", "")) == text\n        ):\n            messages.append(current)\n\n        deduped: list[dict[str, Any]] = []\n        seen: set[str] = set()\n        for item in messages:\n            if not isinstance(item, dict):\n                continue\n            norm_text = self._normalize_context_text_for_model(str(item.get("text", "") or ""))\n            key = f"{item.get(\'sender_id\',\'\')}|{norm_text}"\n            if key in seen:\n                continue\n            seen.add(key)\n\n            decayed = self._candidate_decayed_weight(item, now)\n            if decayed < 0.08 and not self._candidate_should_keep_as_background(item, now):\n                continue\n            item["decayed_weight"] = decayed\n            deduped.append(item)\n\n        messages[:] = deduped[-14:]\n\n        batch["context_info"] = dict(context_info)\n        batch["context_info"]["batch_messages"] = list(messages)\n\n        return False, ""\n'
NEW_BATCH_TEXT = '\n    def _build_group_batch_text(self, messages: list[dict[str, Any]]) -> str:\n        """构造带权重衰减的群聊候选输入。"""\n        now = datetime.now()\n        safe_messages = [m for m in (messages or []) if isinstance(m, dict)]\n\n        for item in safe_messages:\n            try:\n                item["decayed_weight"] = self._candidate_decayed_weight(item, now)\n            except Exception:\n                item["decayed_weight"] = self._candidate_base_weight(item)\n\n        context_info: dict[str, Any] = {"batch_messages": safe_messages}\n        try:\n            for item in reversed(safe_messages):\n                context_info["chat_id"] = str(item.get("chat_id", "") or context_info.get("chat_id", ""))\n                context_info["sender_id"] = str(item.get("sender_id", "") or "")\n                context_info["sender_name"] = str(item.get("sender_name", "") or "")\n                break\n        except Exception:\n            pass\n\n        speaker_context = self._build_weighted_speaker_context(context_info=context_info)\n        focus = [m for m in safe_messages if float(m.get("decayed_weight", 0.0) or 0.0) >= 0.22]\n        background = [m for m in safe_messages if float(m.get("decayed_weight", 0.0) or 0.0) < 0.22]\n\n        lines = [\n            "下面是群聊候选消息。你要按权重和时间衰减来判断要不要说话。",\n            "具体人设、名字、兴趣、口癖全部以“当前人设来源”和最近聊天为准；不要使用代码里的旧默认人设。",\n            "",\n            speaker_context,\n            "",\n            "### 候选权重说明",\n            "权重越高，越可能需要回应；权重低的旧消息只是背景，不要强行接。",\n            "如果多个高权重候选来自不同发言者，先分清他们各自在说什么，只回应最自然的一组。",\n            "不要把低权重旧话题硬接到最新消息上。",\n            "",\n            "### 高权重候选",\n        ]\n\n        if focus:\n            for item in sorted(focus, key=lambda x: float(x.get("decayed_weight", 0.0) or 0.0), reverse=True):\n                name = str(item.get("sender_name", "") or item.get("sender_id", "") or "未知")\n                uid = str(item.get("sender_id", "") or "未知")\n                msg_text = self._normalize_context_text_for_model(str(item.get("text", "") or ""))\n                weight = float(item.get("decayed_weight", 0.0) or 0.0)\n                reason = str(item.get("reply_relevance_reason", "") or item.get("social_gate_reason", "") or "")\n                lines.append(f"- {name}(QQ={uid})：{msg_text} ｜权重={weight:.2f}｜原因={reason[:100]}")\n        else:\n            lines.append("- 无明显高权重候选。")\n\n        lines.append("")\n        lines.append("### 低权重背景")\n        for item in background[-8:]:\n            name = str(item.get("sender_name", "") or item.get("sender_id", "") or "未知")\n            uid = str(item.get("sender_id", "") or "未知")\n            msg_text = self._normalize_context_text_for_model(str(item.get("text", "") or ""))\n            weight = float(item.get("decayed_weight", 0.0) or 0.0)\n            lines.append(f"- {name}(QQ={uid})：{msg_text} ｜权重={weight:.2f}")\n\n        lines.extend([\n            "",\n            "回复决策：",\n            "如果没有高权重候选，宁可不说。",\n            "如果要说，只回应最清晰、最新、权重最高的一组话。",\n            "不能把不同人的话混成一个人，不能把别人之间的“你”默认当成自己。",\n            "如果指代不清，用轻微不确定语气；不要自信编造。",\n            "回复要像真实群友，短一点。",\n        ])\n        return "\\n".join(lines)\n'
NEW_SOCIAL_GATE = '\n    def _social_gate_decide_via_api(\n        self,\n        text: str,\n        context_info: dict[str, Any] | None = None,\n    ) -> dict[str, Any]:\n        """模型社交判断：不写死人设/兴趣，只给动态人设和发言者上下文。"""\n        context_info = context_info or {}\n\n        provider = self.reply_api_provider.strip().lower()\n        api_key = self.reply_api_key.strip()\n        if provider not in {"openai", "deepseek", "qwen"} or not api_key:\n            try:\n                return self._dynamic_persona_fallback_decision(text, context_info, "没有可用 API 做社交判断")\n            except Exception:\n                return {"action": "observe", "confidence": 0.0, "reason": "没有可用 API 做社交判断", "angle": ""}\n\n        raw_text = str(text or "")\n\n        if self.reply_api_model.strip():\n            model_name = self.reply_api_model.strip()\n        elif provider == "deepseek":\n            model_name = "deepseek-v4-pro"\n        elif provider == "qwen":\n            model_name = "qwen-plus"\n        else:\n            model_name = "gpt-4o-mini"\n\n        base_url = self.reply_api_base_url.strip()\n        if provider == "deepseek" and not base_url:\n            base_url = "https://api.deepseek.com"\n        if provider == "deepseek" and base_url.rstrip("/").endswith("/v1"):\n            base_url = base_url.rstrip("/")[:-3].rstrip("/")\n        if provider == "openai" and not base_url:\n            base_url = "https://api.openai.com/v1"\n        if provider == "qwen" and not base_url:\n            base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"\n\n        endpoint = base_url.rstrip("/") + "/chat/completions"\n\n        try:\n            context_block = self._build_context_block(text, context_info)\n        except Exception:\n            context_block = ""\n\n        speaker_context = self._build_weighted_speaker_context(context_info, current_text=raw_text)\n\n        gate_prompt = (\n            "你在做 QQ 群聊社交判断，决定当前机器人账号是否要开口。\\n"\n            "不要写死任何名字、人设、兴趣、口癖；这些只能从用户当前配置的人设原文和最近聊天中推断。\\n"\n            "先分清谁说话、谁在回应谁，再判断是否和 SELF 有关。\\n"\n            "SELF 是当前机器人账号；S1/S2/S3 是不同群友。\\n"\n            "群聊里的‘你/他/她/它/这个’必须根据时间线和 @ 对象推断，不默认指 SELF。\\n"\n            "第三方模型、软件、工具、平台名不自动等于 SELF，除非人设原文明确这么说。\\n"\n            "如果当前消息只是群友之间的普通对话，observe。\\n"\n            "如果当前消息明确评价 SELF 的回复效果、行为、理解能力，candidate 或 reply。\\n"\n            "如果不确定是谁，降低 confidence，不要强行接。\\n"\n            "只输出严格 JSON，不要 Markdown，不要前后解释。\\n"\n            \'{"action":"reply|candidate|observe","confidence":0.0,"reason":"短原因，写清楚当前发言者和指向对象","angle":"如果开口，从什么角度说"}\'\n        )\n\n        user_gate = (\n            f"普通上下文：\\n{context_block[:1400]}\\n\\n"\n            f"发言者和动态人设上下文：\\n{speaker_context[:3200]}\\n\\n"\n            f"当前消息原文：{raw_text[:500]}"\n        )\n\n        payload: dict[str, Any] = {\n            "model": model_name,\n            "messages": [\n                {"role": "system", "content": gate_prompt},\n                {"role": "user", "content": user_gate},\n            ],\n            "max_tokens": 650,\n        }\n        if provider != "deepseek":\n            payload["temperature"] = 0.1\n\n        req = urllib.request.Request(\n            endpoint,\n            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),\n            headers={\n                "Authorization": f"Bearer {api_key}",\n                "Content-Type": "application/json",\n            },\n            method="POST",\n        )\n\n        try:\n            with urllib.request.urlopen(req, timeout=25) as resp:\n                body = json.loads(resp.read().decode("utf-8"))\n            msg = body.get("choices", [{}])[0].get("message", {})\n            content = str(msg.get("content", "") or "").strip()\n\n            if not content:\n                try:\n                    return self._dynamic_persona_fallback_decision(text, context_info, "gate返回空内容")\n                except Exception:\n                    return {"action": "observe", "confidence": 0.0, "reason": "gate返回空内容", "angle": ""}\n\n            if hasattr(self, "_parse_social_gate_response"):\n                data = self._parse_social_gate_response(content)\n            else:\n                match = re.search(r"\\{[\\s\\S]*\\}", content)\n                data = json.loads(match.group(0) if match else content)\n\n            if not isinstance(data, dict):\n                try:\n                    return self._dynamic_persona_fallback_decision(text, context_info, "gate输出无法解析")\n                except Exception:\n                    return {"action": "observe", "confidence": 0.0, "reason": "gate输出无法解析", "angle": ""}\n\n            action = str(data.get("action", "observe")).strip().lower()\n            if action not in {"reply", "candidate", "observe"}:\n                action = "observe"\n\n            try:\n                confidence = float(data.get("confidence", 0.0))\n            except Exception:\n                confidence = 0.0\n            confidence = max(0.0, min(1.0, confidence))\n\n            return {\n                "action": action,\n                "confidence": confidence,\n                "reason": str(data.get("reason", ""))[:160],\n                "angle": str(data.get("angle", ""))[:220],\n            }\n        except Exception as exc:\n            try:\n                return self._dynamic_persona_fallback_decision(text, context_info, f"gate失败：{exc}")\n            except Exception:\n                return {"action": "observe", "confidence": 0.0, "reason": f"gate失败：{exc}", "angle": ""}\n'
OLD_GUARD = '            if has_gate_fields:\n                relevant_messages = [\n                    item for item in messages\n                    if isinstance(item, dict)\n                    and (\n                        int(item.get("reply_relevance", 0) or 0) >= 45\n                        or str(item.get("social_action", "")) in {"reply", "candidate"}\n                    )\n                ]\n                strong_messages = [\n                    item for item in messages\n                    if isinstance(item, dict)\n                    and (\n                        int(item.get("reply_relevance", 0) or 0) >= 70\n                        or (\n                            str(item.get("social_action", "")) == "reply"\n                            and float(item.get("social_confidence", 0.0) or 0.0) >= 0.50\n                        )\n                    )\n                ]\n                if not strong_messages and len(relevant_messages) < 2:\n                    group_skipped += 1\n                    continue'
NEW_GUARD = '            if has_gate_fields:\n                weighted_messages = []\n                for item in messages:\n                    if not isinstance(item, dict):\n                        continue\n                    try:\n                        w = self._candidate_decayed_weight(item)\n                    except Exception:\n                        w = 0.0\n                    if w >= 0.08:\n                        item["decayed_weight"] = w\n                        weighted_messages.append(item)\n\n                strong_messages = [item for item in weighted_messages if float(item.get("decayed_weight", 0.0) or 0.0) >= 0.52]\n                total_weight = sum(float(item.get("decayed_weight", 0.0) or 0.0) for item in weighted_messages)\n\n                # 用权值判断，而不是按候选条数硬压缩/硬截断。\n                if not strong_messages and total_weight < 0.78:\n                    group_skipped += 1\n                    continue\n\n                messages = weighted_messages'


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
        "_persona_runtime_profile_for_model",
        "_speaker_label_for_model",
        "_normalize_context_text_for_model",
        "_candidate_timestamp",
        "_candidate_base_weight",
        "_candidate_decayed_weight",
        "_candidate_should_keep_as_background",
        "_build_weighted_speaker_context",
    ]
    for name in names:
        method_text = extract_one_method(HELPERS, name)
        if method_range(src, name) is not None:
            src = replace_method(src, name, method_text)
        else:
            target = "_add_group_message_to_batch" if method_range(src, "_add_group_message_to_batch") else "_handle_message"
            src = insert_before(src, target, method_text)
    return src


def patch_poll_pending_weight_guard(src: str) -> str:
    if OLD_GUARD in src:
        return src.replace(OLD_GUARD, NEW_GUARD, 1)

    old2 = OLD_GUARD.replace(">= 70", ">= 60").replace(">= 0.50", ">= 0.45")
    if old2 in src:
        return src.replace(old2, NEW_GUARD, 1)

    print("⚠️ 没找到 poll_pending 权值守门片段，已跳过；候选权重仍会进入 batch prompt。")
    return src


def patch_reply_prompt_generic(src: str) -> str:
    addition = (
        " 群聊中必须先分清发言者和指代对象；不要把不同 QQ 号的人当成同一个人，"
        "不要把群友之间的“你/他/她/它”默认当成自己。具体名字、人设、兴趣、口癖都只从当前配置的人设原文和最近聊天推断，"
        "不要使用代码里的旧默认人设。候选消息有时间衰减权重，低权重旧消息只是背景，不要强行接。"
    )
    if addition in src:
        return src

    for marker in (
        "不要输出 Markdown、标题、编号、解释性前言。",
        "群聊里要结合上下文，合并共同话题，不要逐条复读。",
        "回复要短，像 QQ 聊天，不要写文章。",
    ):
        if marker in src:
            return src.replace(marker, marker + addition, 1)
    return src


def main() -> None:
    if not TARGET.exists():
        raise SystemExit(f"找不到文件：{TARGET}")

    src = TARGET.read_text(encoding="utf-8")
    backup = TARGET.with_suffix(".py.bak_dynamic_speaker_weight")
    backup.write_text(src, encoding="utf-8")

    src = ensure_helpers(src)

    if method_range(src, "_add_group_message_to_batch") is not None:
        src = replace_method(src, "_add_group_message_to_batch", NEW_ADD_BATCH)
    else:
        raise RuntimeError("找不到 _add_group_message_to_batch")

    if method_range(src, "_build_group_batch_text") is not None:
        src = replace_method(src, "_build_group_batch_text", NEW_BATCH_TEXT)
    else:
        raise RuntimeError("找不到 _build_group_batch_text")

    if method_range(src, "_social_gate_decide_via_api") is not None:
        src = replace_method(src, "_social_gate_decide_via_api", NEW_SOCIAL_GATE)
    else:
        src = insert_before(src, "_should_reply_to_group_message", NEW_SOCIAL_GATE)

    src = patch_poll_pending_weight_guard(src)
    src = patch_reply_prompt_generic(src)

    compile(src, str(TARGET), "exec")
    TARGET.write_text(src, encoding="utf-8")

    print("✅ 已改成动态人设 + 候选权值衰减")
    print("不再把名字、人设、兴趣点写死；全部从 custom_prompt 和最近聊天推断。")
    print("候选回复不再按条数硬压缩，改为 candidate_weight + 半衰期衰减。")
    print("可调参数：QQ_CANDIDATE_HALF_LIFE_SEC，默认 22 秒。")
    print(f"备份文件：{backup}")
    print("下一步：")
    print("  python -m py_compile .\\src\\clawmini\\tools\\qq_auto_reply.py")
    print("  python app.py")


if __name__ == "__main__":
    main()
