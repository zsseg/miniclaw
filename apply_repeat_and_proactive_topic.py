#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import ast
from pathlib import Path


PROJECT_ROOT = Path.cwd()
TARGET = PROJECT_ROOT / "src" / "clawmini" / "tools" / "qq_auto_reply.py"

HELPERS = '\n    def _normalize_repeat_phrase(self, text: str) -> str:\n        """把消息归一化成适合判断复读的短文本。"""\n        raw = str(text or "").strip()\n        raw = re.sub(r"\\[CQ:at,qq=([0-9]+)[^\\]]*\\]", "", raw)\n        raw = re.sub(r"\\[CQ:reply[^\\]]*\\]", "", raw)\n        raw = re.sub(r"\\[CQ:image[^\\]]*\\]", "", raw)\n        raw = re.sub(r"\\[CQ:face[^\\]]*\\]", "", raw)\n        raw = re.sub(r"\\[CQ:forward[^\\]]*\\]", "", raw)\n        raw = re.sub(r"\\s+", "", raw)\n        raw = raw.strip("，。！？!?~～…、,.；;：:（）()[]【】「」『』\\"\'")\n        return raw\n\n    def _repeat_phrase_is_safe_to_join(self, phrase: str) -> bool:\n        """复读内容的基础过滤：只跟短句，不跟链接/命令/CQ/超长内容。"""\n        p = str(phrase or "").strip()\n        if not p:\n            return False\n        if len(p) > 20:\n            return False\n        if "[CQ:" in p:\n            return False\n        if re.search(r"https?://|www\\.|\\.com|\\.cn|\\.net", p, re.I):\n            return False\n        if p.startswith(("/", "!", "！", "#")):\n            return False\n        if re.fullmatch(r"\\d{4,}", p):\n            return False\n        return True\n\n    def _recent_repeat_chain_stats(\n        self,\n        chat_id: str,\n        current_sender_id: str,\n        current_text: str,\n    ) -> dict[str, Any]:\n        """统计最近是否形成“大家复读”。"""\n        phrase = self._normalize_repeat_phrase(current_text)\n        users: set[str] = set()\n        count = 0\n\n        if not self._repeat_phrase_is_safe_to_join(phrase):\n            return {"phrase": phrase, "count": 0, "user_count": 0, "users": set()}\n\n        def consider(sender_id: str, text: str) -> None:\n            nonlocal count, users\n            p = self._normalize_repeat_phrase(text)\n            if p and p == phrase:\n                count += 1\n                if sender_id:\n                    users.add(str(sender_id))\n\n        consider(str(current_sender_id or ""), current_text)\n\n        try:\n            batch = self.pending_group_batches.get(str(chat_id), {})\n            if isinstance(batch, dict):\n                for item in batch.get("messages", [])[-12:]:\n                    if not isinstance(item, dict):\n                        continue\n                    consider(str(item.get("sender_id", "") or ""), str(item.get("text", "") or ""))\n        except Exception:\n            pass\n\n        try:\n            for item in self.recent_messages.get(str(chat_id), [])[-18:]:\n                if not isinstance(item, dict):\n                    continue\n                if str(item.get("sender_id", "") or "") in {"SELF", "BOT", "ME", "group_batch"}:\n                    continue\n                consider(str(item.get("sender_id", "") or ""), str(item.get("text", "") or ""))\n        except Exception:\n            pass\n\n        return {"phrase": phrase, "count": count, "user_count": len(users), "users": users}\n\n    def _should_join_repeat_chain(\n        self,\n        chat_id: str,\n        sender_id: str,\n        text: str,\n        context_info: dict[str, Any] | None = None,\n    ) -> tuple[bool, str, str]:\n        """判断是否参与大家复读。"""\n        context_info = context_info or {}\n\n        if context_info.get("mentioned") or context_info.get("explicit_self"):\n            return False, "", ""\n\n        stats = self._recent_repeat_chain_stats(chat_id, sender_id, text)\n        phrase = str(stats.get("phrase", "") or "")\n        count = int(stats.get("count", 0) or 0)\n        user_count = int(stats.get("user_count", 0) or 0)\n\n        if not self._repeat_phrase_is_safe_to_join(phrase):\n            return False, "", ""\n\n        try:\n            if self._is_echo_of_recent_bot_reply(chat_id, phrase):\n                return False, "", ""\n        except Exception:\n            pass\n\n        if not (user_count >= 2 and count >= 2):\n            return False, "", ""\n\n        if not hasattr(self, "_last_repeat_join"):\n            self._last_repeat_join = {}\n\n        key = f"{chat_id}:{phrase}"\n        now = datetime.now()\n\n        try:\n            cooldown = float(os.getenv("QQ_REPEAT_JOIN_COOLDOWN_SEC", "55"))\n        except Exception:\n            cooldown = 55.0\n        cooldown = max(20.0, min(cooldown, 180.0))\n\n        last = self._last_repeat_join.get(key)\n        if isinstance(last, datetime) and (now - last).total_seconds() < cooldown:\n            return False, "", ""\n\n        self._last_repeat_join[key] = now\n        return True, phrase, f"检测到多人复读：{phrase}"\n\n    def _proactive_topics_enabled(self) -> bool:\n        raw = str(os.getenv("QQ_PROACTIVE_TOPIC_ENABLED", "1")).strip().lower()\n        return raw not in {"0", "false", "no", "off", "关", "关闭"}\n\n    def _proactive_topic_interval_sec(self) -> float:\n        try:\n            value = float(os.getenv("QQ_PROACTIVE_TOPIC_INTERVAL_SEC", "1200"))\n        except Exception:\n            value = 1200.0\n        return max(300.0, min(value, 7200.0))\n\n    def _build_recent_context_for_proactive_topic(self, chat_id: str) -> str:\n        """给主动开话题用的最近上下文，不写死人设/兴趣。"""\n        lines: list[str] = []\n        try:\n            for item in self.recent_messages.get(str(chat_id), [])[-12:]:\n                if not isinstance(item, dict):\n                    continue\n                sender_id = str(item.get("sender_id", "") or "")\n                sender_name = str(item.get("sender_name", "") or sender_id or "群友")\n                text = str(item.get("text", "") or "").strip()\n                reply = str(item.get("reply", "") or "").strip()\n                if text:\n                    clean = text\n                    clean = re.sub(r"\\[CQ:image[^\\]]*\\]", "[图片]", clean)\n                    clean = re.sub(r"\\[CQ:face[^\\]]*\\]", "[表情]", clean)\n                    clean = re.sub(r"\\s+", " ", clean).strip()\n                    lines.append(f"{sender_name}: {clean[:120]}")\n                if reply:\n                    lines.append(f"SELF: {reply[:120]}")\n        except Exception:\n            pass\n\n        if not lines:\n            return "最近没有可用群聊上下文。"\n\n        return "\\n".join(lines[-10:])\n\n    def _generate_proactive_topic_text(self, chat_id: str) -> str:\n        """生成一个主动开话题短句。\n\n        不使用固定兴趣点；只能从 custom_prompt 和最近聊天中找灵感。\n        """\n        provider = self.reply_api_provider.strip().lower()\n        api_key = self.reply_api_key.strip()\n        if provider not in {"openai", "deepseek", "qwen"} or not api_key:\n            return ""\n\n        if self.reply_api_model.strip():\n            model_name = self.reply_api_model.strip()\n        elif provider == "deepseek":\n            model_name = "deepseek-v4-pro"\n        elif provider == "qwen":\n            model_name = "qwen-plus"\n        else:\n            model_name = "gpt-4o-mini"\n\n        base_url = self.reply_api_base_url.strip()\n        if provider == "deepseek" and not base_url:\n            base_url = "https://api.deepseek.com"\n        if provider == "deepseek" and base_url.rstrip("/").endswith("/v1"):\n            base_url = base_url.rstrip("/")[:-3].rstrip("/")\n        if provider == "openai" and not base_url:\n            base_url = "https://api.openai.com/v1"\n        if provider == "qwen" and not base_url:\n            base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"\n\n        endpoint = base_url.rstrip("/") + "/chat/completions"\n\n        custom = str(getattr(self, "custom_prompt", "") or "").strip()\n        recent = self._build_recent_context_for_proactive_topic(chat_id)\n\n        system_prompt = (\n            "你要为一个 QQ 群里的机器人账号生成一句主动开话题的话。\\n"\n            "不要写死任何名字、人设、兴趣、口癖；这些只能从用户当前配置的人设和最近群聊里推断。\\n"\n            "这句话应该像真实群友自然冒泡，不要像客服，不要像公告，不要说“我来开启话题”。\\n"\n            "可以基于当前人设里的兴趣，也可以基于最近群聊里没聊完的话题，也可以轻轻吐槽一句。\\n"\n            "不要强行问很正式的问题；不要@任何人；不要提系统规则；不要解释为什么开话题。\\n"\n            "长度 8~35 个中文字符。只输出要发送的那一句。"\n        )\n\n        user_prompt = (\n            f"当前人设原文：\\n{custom[:1600] if custom else \'无额外人设配置\'}\\n\\n"\n            f"最近群聊：\\n{recent[:1800]}\\n\\n"\n            "生成一句可以在群里自然发出的开话题短句。"\n        )\n\n        payload: dict[str, Any] = {\n            "model": model_name,\n            "messages": [\n                {"role": "system", "content": system_prompt},\n                {"role": "user", "content": user_prompt},\n            ],\n            "max_tokens": 120,\n        }\n        if provider != "deepseek":\n            payload["temperature"] = 0.7\n\n        req = urllib.request.Request(\n            endpoint,\n            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),\n            headers={\n                "Authorization": f"Bearer {api_key}",\n                "Content-Type": "application/json",\n            },\n            method="POST",\n        )\n\n        try:\n            with urllib.request.urlopen(req, timeout=20) as resp:\n                body = json.loads(resp.read().decode("utf-8"))\n            msg = body.get("choices", [{}])[0].get("message", {})\n            text = str(msg.get("content", "") or "").strip()\n            text = re.sub(r"^```.*?\\n", "", text, flags=re.S).strip()\n            text = text.strip("` \\n\\r\\t")\n            text = re.sub(r"\\s+", " ", text).strip()\n            if not text:\n                return ""\n            if hasattr(self, "_is_generic_api_fallback_reply") and self._is_generic_api_fallback_reply(text):\n                return ""\n            if len(text) > 80:\n                text = text[:80].rstrip("，。！？,.!? ")\n            return text\n        except Exception:\n            return ""\n\n    def _maybe_send_proactive_topic(self) -> dict[str, Any] | None:\n        """在群聊很久没回复时，偶尔主动开启话题。\n\n        这个功能有长冷却，不会频繁打断。\n        """\n        if not self._proactive_topics_enabled():\n            return None\n\n        if self.paused or not self.enabled:\n            return None\n\n        if not hasattr(self, "_last_proactive_topic"):\n            self._last_proactive_topic = {}\n\n        try:\n            if self.pending_group_batches:\n                return None\n        except Exception:\n            pass\n\n        interval = self._proactive_topic_interval_sec()\n        now = datetime.now()\n\n        groups = list(getattr(self, "target_group_ids", []) or [])\n        if not groups:\n            return None\n\n        for chat_id in groups:\n            chat_id = str(chat_id)\n            last_topic = self._last_proactive_topic.get(chat_id)\n            if isinstance(last_topic, datetime) and (now - last_topic).total_seconds() < interval:\n                continue\n\n            last_reply = self.last_auto_reply.get(chat_id)\n            if isinstance(last_reply, datetime) and (now - last_reply).total_seconds() < interval:\n                continue\n\n            try:\n                if self._is_in_cooldown(chat_id):\n                    continue\n            except Exception:\n                pass\n\n            text = self._generate_proactive_topic_text(chat_id)\n            if not text:\n                continue\n\n            send_result = self._send_via_gateway(chat_id=chat_id, reply=text, message_type="group")\n            if not send_result.success:\n                continue\n\n            self._last_proactive_topic[chat_id] = now\n            self.last_auto_reply[chat_id] = now\n\n            input_text = "[主动开话题]"\n            self._append_log(chat_id, "proactive_topic", input_text, text)\n            context_info = {\n                "source": "group",\n                "chat_id": chat_id,\n                "sender_id": "proactive_topic",\n                "proactive_topic": True,\n            }\n            self._remember_recent_exchange(chat_id, "group", "proactive_topic", input_text, text, context_info)\n\n            return {\n                "source": "group",\n                "message_type": "group",\n                "chat_id": chat_id,\n                "sender_id": "proactive_topic",\n                "sender_name": "主动开话题",\n                "input_text": input_text,\n                "reply": text,\n                "reply_parts": [text],\n                "kind": "proactive_topic",\n            }\n\n        return None\n'
REPEAT_GUARD = '        # 大家复读时，允许机器人偶尔参与一次。\n        try:\n            join_repeat, repeat_text, repeat_reason = self._should_join_repeat_chain(\n                chat_id=chat_id,\n                sender_id=str(context_info.get("sender_id", "") or ""),\n                text=text,\n                context_info=context_info,\n            )\n            if join_repeat and repeat_text:\n                context_info["force_reply_text"] = repeat_text\n                context_info["reply_relevance"] = 95\n                context_info["reply_relevance_reason"] = repeat_reason\n                context_info["social_action"] = "reply"\n                context_info["social_confidence"] = 0.95\n                return True, repeat_reason\n        except Exception:\n            pass\n\n'
FORCE_REPLY_SNIPPET = '        if context_info and context_info.get("force_reply_text"):\n            forced_reply = str(context_info.get("force_reply_text", "")).strip()\n            if forced_reply:\n                return [forced_reply[:120]]\n\n'
POLL_SNIPPET = '        # 如果没有待回复内容，且长时间没有主动说话，可以偶尔自然开启一个话题。\n        try:\n            if not sent_reply_records:\n                proactive_record = self._maybe_send_proactive_topic()\n                if proactive_record:\n                    sent_reply_records.append(proactive_record)\n                    group_sent += 1\n        except Exception:\n            pass\n\n'


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
        "_normalize_repeat_phrase",
        "_repeat_phrase_is_safe_to_join",
        "_recent_repeat_chain_stats",
        "_should_join_repeat_chain",
        "_proactive_topics_enabled",
        "_proactive_topic_interval_sec",
        "_build_recent_context_for_proactive_topic",
        "_generate_proactive_topic_text",
        "_maybe_send_proactive_topic",
    ]
    for name in names:
        method_text = extract_one_method(HELPERS, name)
        if method_range(src, name) is not None:
            src = replace_method(src, name, method_text)
        else:
            target = "_should_reply_to_group_message" if method_range(src, "_should_reply_to_group_message") else "_handle_message"
            src = insert_before(src, target, method_text)
    return src


def insert_after_docstring(src: str, method_name: str, snippet: str) -> str:
    if snippet.strip() in src:
        return src

    tree = ast.parse(src)
    target = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == method_name:
            target = node
            break
    if target is None or target.end_lineno is None:
        raise RuntimeError(f"找不到方法：{method_name}")

    insert_lineno = target.lineno + 1
    if (
        target.body
        and isinstance(target.body[0], ast.Expr)
        and isinstance(getattr(target.body[0], "value", None), ast.Constant)
        and isinstance(target.body[0].value.value, str)
    ):
        insert_lineno = target.body[0].end_lineno + 1

    lines = src.splitlines()
    lines[insert_lineno - 1:insert_lineno - 1] = snippet.rstrip("\n").splitlines()
    return "\n".join(lines) + "\n"


def patch_should_reply_for_repeat(src: str) -> str:
    if "大家复读时，允许机器人偶尔参与一次" in src:
        return src

    rng = method_range(src, "_should_reply_to_group_message")
    if rng is None:
        raise RuntimeError("找不到 _should_reply_to_group_message")

    start, end = rng
    lines = src.splitlines()
    method = lines[start - 1:end]

    insert_at = None
    for i, line in enumerate(method):
        if "context_info = context_info or {}" in line:
            insert_at = i + 1
            break

    if insert_at is None:
        insert_at = 1

    method[insert_at:insert_at] = REPEAT_GUARD.rstrip("\n").splitlines()
    new_lines = lines[: start - 1] + method + lines[end:]
    return "\n".join(new_lines) + "\n"


def patch_build_reply_parts_force(src: str) -> str:
    if 'context_info and context_info.get("force_reply_text")' in src:
        return src
    return insert_after_docstring(src, "_build_reply_parts", FORCE_REPLY_SNIPPET)


def patch_poll_pending_proactive(src: str) -> str:
    if "_maybe_send_proactive_topic()" in src:
        return src

    rng = method_range(src, "_poll_pending")
    if rng is None:
        raise RuntimeError("找不到 _poll_pending")

    start, end = rng
    lines = src.splitlines()
    method = lines[start - 1:end]

    insert_at = None
    for i, line in enumerate(method):
        if line.strip().startswith("output = ("):
            insert_at = i
            break

    if insert_at is None:
        raise RuntimeError("没找到 _poll_pending 里的 output = ( 插入点。")

    method[insert_at:insert_at] = POLL_SNIPPET.rstrip("\n").splitlines()
    new_lines = lines[: start - 1] + method + lines[end:]
    return "\n".join(new_lines) + "\n"


def main() -> None:
    if not TARGET.exists():
        raise SystemExit(f"找不到文件：{TARGET}")

    src = TARGET.read_text(encoding="utf-8")
    backup = TARGET.with_suffix(".py.bak_repeat_and_proactive")
    backup.write_text(src, encoding="utf-8")

    src = ensure_helpers(src)
    src = patch_should_reply_for_repeat(src)
    src = patch_build_reply_parts_force(src)
    src = patch_poll_pending_proactive(src)

    compile(src, str(TARGET), "exec")
    TARGET.write_text(src, encoding="utf-8")

    print("✅ 已添加：参与复读 + 偶尔主动开话题")
    print("复读：多人复读短句时，机器人会按冷却偶尔复读一次，不会跟纯图片/CQ/链接/超长内容。")
    print("开话题：没有待回复内容且长时间没说话时，会根据 custom_prompt 和最近聊天生成一句自然话题。")
    print(f"备份文件：{backup}")
    print("下一步：")
    print("  python -m py_compile .\\src\\clawmini\\tools\\qq_auto_reply.py")
    print("  python app.py")
    print()
    print("可调参数：")
    print('  $env:QQ_REPEAT_JOIN_COOLDOWN_SEC="55"')
    print('  $env:QQ_PROACTIVE_TOPIC_ENABLED="1"')
    print('  $env:QQ_PROACTIVE_TOPIC_INTERVAL_SEC="1200"')


if __name__ == "__main__":
    main()
