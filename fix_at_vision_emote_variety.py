#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import ast
from pathlib import Path


PROJECT_ROOT = Path.cwd()
TARGET = PROJECT_ROOT / "src" / "clawmini" / "tools" / "qq_auto_reply.py"

AT_HELPERS = '\n    def _parse_leading_numeric_at_reply(self, reply: str) -> tuple[str, str] | None:\n        """解析模型回复里开头的 @数字 / CQ at。"""\n        text = str(reply or "").strip()\n        if not text:\n            return None\n\n        m = re.match(r"^\\[CQ:at,qq=(\\d+)[^\\]]*\\]\\s*(.*)$", text, flags=re.I | re.S)\n        if m:\n            return m.group(1), str(m.group(2) or "").strip()\n\n        m = re.match(r"^@(\\d{5,12})(?:\\s+([\\s\\S]*))?$", text)\n        if m:\n            return m.group(1), str(m.group(2) or "").strip()\n\n        return None\n\n    def _send_group_at_text_segments_generic(self, chat_id: str, target_qq: str, text: str = "") -> ToolResult:\n        """用 OneBot 消息段发送群聊 @ + 可选文本。\n\n        允许只有 @，不再拦截。\n        """\n        group_id = str(chat_id or "").strip()\n        qq = str(target_qq or "").strip()\n        plain_text = str(text or "").strip()\n\n        if not group_id or not qq:\n            return ToolResult(False, "缺少群号或 @ 对象。")\n\n        if plain_text:\n            try:\n                plain_text = self._sanitize_reply_before_send(plain_text)\n            except Exception:\n                pass\n\n        if getattr(self, "gateway_mode", "") == "managed":\n            try:\n                self._refresh_managed_gateway_config()\n            except Exception:\n                pass\n\n        base_candidates: list[str] = []\n        for raw_base in (\n            str(getattr(getattr(self, "gateway", None), "api_base_url", "") or "").strip(),\n            str(getattr(self, "managed_api_base_url", "") or "").strip(),\n        ):\n            if not raw_base:\n                continue\n            base = raw_base.rstrip("/")\n            if base and base not in base_candidates:\n                base_candidates.append(base)\n            if "/plugin/" in base:\n                root = base.split("/plugin/", 1)[0].rstrip("/")\n                if root and root not in base_candidates:\n                    base_candidates.append(root)\n\n        if not base_candidates:\n            return ToolResult(False, "没有可用 NapCat API 地址，无法发送 @ 消息段。")\n\n        token = (\n            str(getattr(getattr(self, "gateway", None), "access_token", "") or "").strip()\n            or str(getattr(self, "managed_access_token", "") or "").strip()\n        )\n\n        segments = [{"type": "at", "data": {"qq": int(qq) if qq.isdigit() else qq}}]\n        if plain_text:\n            segments.append({"type": "text", "data": {"text": " " + plain_text}})\n\n        payload = {\n            "group_id": int(group_id) if group_id.isdigit() else group_id,\n            "message": segments,\n            "auto_escape": False,\n        }\n\n        last_error = ""\n        for base in base_candidates:\n            endpoint = base.rstrip("/") + "/send_group_msg"\n            headers = {"Content-Type": "application/json"}\n            if token:\n                headers["Authorization"] = f"Bearer {token}"\n\n            req = urllib.request.Request(\n                endpoint,\n                data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),\n                headers=headers,\n                method="POST",\n            )\n\n            try:\n                with urllib.request.urlopen(req, timeout=12) as resp:\n                    raw = resp.read().decode("utf-8", errors="replace")\n\n                try:\n                    body = json.loads(raw)\n                except Exception:\n                    body = {"raw": raw}\n\n                ok = True\n                if isinstance(body, dict):\n                    if str(body.get("status", "")).lower() == "failed":\n                        ok = False\n                    if "retcode" in body:\n                        try:\n                            ok = int(body.get("retcode")) == 0\n                        except Exception:\n                            ok = False\n\n                meta_reply = f"@{qq}" + (f" {plain_text}" if plain_text else "")\n                if ok:\n                    return ToolResult(\n                        True,\n                        "ok",\n                        {\n                            "chat_id": group_id,\n                            "message_type": "group",\n                            "reply": meta_reply,\n                            "plain_reply": plain_text,\n                            "at_qq": qq,\n                            "endpoint": endpoint,\n                            "segment_message": True,\n                            "segments": segments,\n                            "response": raw,\n                            "parsed_response": body,\n                        },\n                    )\n\n                last_error = f"{endpoint} 返回失败：{raw[:500]}"\n            except Exception as exc:\n                last_error = f"{endpoint} 请求失败：{exc}"\n\n        return ToolResult(False, last_error or "发送 @ 消息段失败。")\n\n    def _maybe_send_leading_at_as_segment(\n        self,\n        chat_id: str,\n        reply: str,\n        message_type: str = "group",\n    ) -> ToolResult | None:\n        """如果普通回复以 @数字 开头，转换成真正 OneBot at 消息段。\n\n        允许只有 @QQ，没有正文。\n        """\n        if str(message_type or "") != "group":\n            return None\n\n        parsed = self._parse_leading_numeric_at_reply(reply)\n        if not parsed:\n            return None\n\n        qq, rest = parsed\n        return self._send_group_at_text_segments_generic(chat_id, qq, rest)\n'
SEND_AT_SNIPPET = '        # 普通文本里的 @123456 不会变成真正 QQ @；这里转换成 OneBot at 段。\n        # 允许只有 @，不会拦截。\n        try:\n            _locals = locals()\n            _args = _locals.get("args", ())\n            _kwargs = _locals.get("kwargs", {})\n            _chat_id = _kwargs.get("chat_id") if isinstance(_kwargs, dict) else None\n            _reply = _kwargs.get("reply") if isinstance(_kwargs, dict) else None\n            _message_type = _kwargs.get("message_type") if isinstance(_kwargs, dict) else None\n\n            if _chat_id is None:\n                _chat_id = _locals.get("chat_id")\n            if _reply is None:\n                _reply = _locals.get("reply")\n            if _message_type is None:\n                _message_type = _locals.get("message_type")\n\n            if _chat_id is None and len(_args) >= 1:\n                _chat_id = _args[0]\n            if _reply is None and len(_args) >= 2:\n                _reply = _args[1]\n            if _message_type is None and len(_args) >= 3:\n                _message_type = _args[2]\n\n            _at_result = self._maybe_send_leading_at_as_segment(\n                chat_id=str(_chat_id or ""),\n                reply=str(_reply or ""),\n                message_type=str(_message_type or ""),\n            )\n            if _at_result is not None:\n                return _at_result\n        except Exception:\n            pass\n\n'
VISION_HELPERS = '\n    def _extract_obvious_text_from_image_descriptions(self, descriptions: list[str]) -> str:\n        """从识图结果中提取清晰的图片文字。"""\n        for desc in descriptions or []:\n            s = str(desc or "").strip()\n            if not s:\n                continue\n\n            m = re.search(r"可见文字[:：]\\s*(.*?)(?:\\s+文字清晰度[:：]|\\s+可见内容[:：]|\\s+不确定点[:：]|$)", s)\n            if not m:\n                m = re.search(r"(?:文字|图中文字)[:：]\\s*(.*?)(?:\\s+文字清晰度[:：]|\\s+可见内容[:：]|\\s+不确定点[:：]|$)", s)\n            if not m:\n                continue\n\n            text = m.group(1).strip(" \\n\\r\\t。；;，,")\n            if not text:\n                continue\n            if any(x in text for x in ("无", "没有", "看不清", "不清楚", "无法识别")) and len(text) <= 8:\n                continue\n\n            clarity = ""\n            m2 = re.search(r"文字清晰度[:：]\\s*(高|中|低|无)", s)\n            if m2:\n                clarity = m2.group(1)\n            if clarity in {"低", "无"}:\n                continue\n\n            text = re.sub(r"\\s+", "", text)\n            if 1 <= len(text) <= 50:\n                return text\n\n        return ""\n\n    def _summarize_image_vision_for_log(self, descriptions: list[str]) -> str:\n        """把识图结果压成方便看日志的一行。"""\n        descs = [str(x or "").strip() for x in (descriptions or []) if str(x or "").strip()]\n        if not descs:\n            return "无识别结果；可能未配置 DASHSCOPE_API_KEY、图片下载失败，或识图返回为空。"\n\n        visible_text = self._extract_obvious_text_from_image_descriptions(descs)\n        first = descs[0]\n\n        clarity = ""\n        m = re.search(r"文字清晰度[:：]\\s*(高|中|低|无)", first)\n        if m:\n            clarity = m.group(1)\n\n        content = ""\n        m2 = re.search(r"可见内容[:：]\\s*(.*?)(?:\\s+不确定点[:：]|\\s+可能情绪[:：]|\\s+采信度[:：]|$)", first)\n        if m2:\n            content = m2.group(1).strip()\n\n        parts = []\n        if visible_text:\n            parts.append(f"文字={visible_text}")\n        else:\n            parts.append("文字=无/不清楚")\n        if clarity:\n            parts.append(f"清晰度={clarity}")\n        if content:\n            parts.append(f"内容={content[:80]}")\n        else:\n            parts.append(f"摘要={first[:120]}")\n\n        return " | ".join(parts)\n\n    def _log_system_debug(self, message: str) -> None:\n        """尽力把调试信息打到 UI/控制台。"""\n        msg = str(message or "").strip()\n        if not msg:\n            return\n\n        # 先控制台，保证用户能看到。\n        try:\n            print(msg)\n        except Exception:\n            pass\n\n        callbacks = []\n        for attr in ("event_callback", "log_callback", "status_callback", "on_event"):\n            cb = getattr(self, attr, None)\n            if callable(cb):\n                callbacks.append(cb)\n\n        for cb in callbacks:\n            for payload in (\n                ("system", msg),\n                ("系统", msg),\n                {"level": "info", "type": "system", "title": "系统", "message": msg},\n                msg,\n            ):\n                try:\n                    if isinstance(payload, tuple):\n                        cb(*payload)\n                    else:\n                        cb(payload)\n                    return\n                except Exception:\n                    continue\n\n    def _log_image_vision_debug(\n        self,\n        chat_id: str,\n        sender_id: str,\n        image_index: int,\n        descriptions: list[str],\n        ref: str = "",\n    ) -> None:\n        """识图完成后输出可见文字/摘要，方便判断有没有提取。"""\n        summary = self._summarize_image_vision_for_log(descriptions)\n        gid = str(chat_id or "?")\n        uid = str(sender_id or "?")\n        self._log_system_debug(f"[QQVision] group/{gid} user/{uid} image#{image_index}: {summary}")\n'
START_IMAGE_JOB = '\n    def _start_image_observation_job(\n        self,\n        image_refs: list[str],\n        user_text: str = "",\n        chat_id: str = "",\n        sender_id: str = "",\n    ) -> None:\n        """后台预热识图，不直接触发回复；完成后输出 QQVision 日志。"""\n        self._ensure_image_observation_state()\n\n        refs = [str(ref or "").strip() for ref in (image_refs or []) if str(ref or "").strip()]\n        if not refs:\n            return\n\n        for index, ref in enumerate(refs[:3], start=1):\n            key = self._image_observation_key(ref)\n            if not key:\n                continue\n            if key in self._image_observation_cache or key in self._image_observation_pending:\n                # 已经有结果时，也打一行摘要，方便你确认它确实提取过。\n                try:\n                    cached = self._image_observation_cache.get(key, {})\n                    if isinstance(cached, dict) and cached.get("descriptions"):\n                        self._log_image_vision_debug(chat_id, sender_id, index, cached.get("descriptions", []), ref)\n                except Exception:\n                    pass\n                continue\n\n            self._image_observation_pending.add(key)\n\n            def _worker(_ref: str = ref, _key: str = key, _index: int = index, _user_text: str = user_text) -> None:\n                descriptions: list[str] = []\n                try:\n                    descriptions = self._describe_images_with_qwen_vl([_ref], _user_text)\n                    self._image_observation_cache[_key] = {\n                        "descriptions": descriptions,\n                        "created_at": datetime.now(),\n                        "ref": _ref,\n                    }\n                except Exception as exc:\n                    descriptions = [f"图片识别失败：{exc}"]\n                    self._image_observation_cache[_key] = {\n                        "descriptions": descriptions,\n                        "created_at": datetime.now(),\n                        "ref": _ref,\n                    }\n                finally:\n                    try:\n                        self._image_observation_pending.discard(_key)\n                    except Exception:\n                        pass\n                    try:\n                        self._log_image_vision_debug(chat_id, sender_id, _index, descriptions, _ref)\n                    except Exception:\n                        pass\n\n            try:\n                threading.Thread(target=_worker, daemon=True).start()\n            except Exception:\n                try:\n                    self._image_observation_pending.discard(key)\n                except Exception:\n                    pass\n'
VISION_DESCRIBE = '\n    def _describe_images_with_qwen_vl(self, image_refs: list[str], user_text: str = "") -> list[str]:\n        """用 Qwen-VL 单独识图，返回低采信度图片线索。\n\n        会单独提取“可见文字/文字清晰度”，便于处理带字表情或截图。\n        """\n        api_key = os.getenv("DASHSCOPE_API_KEY", "").strip()\n        if not api_key:\n            return []\n\n        base_url = os.getenv(\n            "QWEN_VL_BASE_URL",\n            "https://dashscope.aliyuncs.com/compatible-mode/v1",\n        ).strip().rstrip("/")\n        model = os.getenv("QWEN_VL_MODEL", "qwen-vl-plus").strip() or "qwen-vl-plus"\n        endpoint = base_url + "/chat/completions"\n        descriptions: list[str] = []\n\n        for index, ref in enumerate(image_refs[:3], start=1):\n            image_part = self._image_ref_to_content_part(ref)\n            if image_part is None:\n                continue\n\n            prompt = (\n                "你在为 QQ 群聊机器人做图片识别。请务必保守，不要过度解读。\\n"\n                "图片可能是表情、梗图、截图、头像、普通照片，也可能只是无语境图片。\\n"\n                "重点：如果图里有清晰可见文字，请准确抄出文字；文字不清楚就写“无”。\\n"\n                "可见文字可以作为较可靠的视觉事实；但图片真正想表达的含义仍然必须低置信处理。\\n"\n                "不要擅自判断图片真正想表达的意思；如果要说含义，必须用“可能/像是/不确定”。\\n"\n                "如果图片没什么明确内容，就直接说信息量低，不要硬解释。\\n"\n                "按格式输出，简短中文：\\n"\n                "可见文字：逐字抄出清晰文字；没有或看不清写“无”。\\n"\n                "文字清晰度：高/中/低/无。\\n"\n                "可见内容：确定能看到的主体、表情、动作。\\n"\n                "不确定点：可能看错、需要上下文、无法确认的内容；没有就写“无明显”。\\n"\n                "可能情绪：低置信度推测，例如“可能是在调侃/疑惑/无语”；不要下定论。\\n"\n                "采信度：高/中/低。只有文字清楚、主体明确时才能高；梗图的含义通常为中或低。\\n"\n                "不要输出客套话，不要说你是模型。"\n            )\n            if user_text:\n                prompt += f"\\n用户配文：{user_text}\\n可以结合配文，但仍不要过度解读图片本意。"\n\n            payload = {\n                "model": model,\n                "temperature": 0.0,\n                "max_tokens": 420,\n                "messages": [\n                    {"role": "user", "content": [{"type": "text", "text": prompt}, image_part]}\n                ],\n            }\n\n            req = urllib.request.Request(\n                endpoint,\n                data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),\n                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},\n                method="POST",\n            )\n\n            try:\n                with urllib.request.urlopen(req, timeout=45) as resp:\n                    body = json.loads(resp.read().decode("utf-8"))\n                content = str(body["choices"][0]["message"]["content"]).strip()\n                if content:\n                    content = re.sub(r"\\s+", " ", content).strip()\n                    descriptions.append(f"第{index}张图片低采信度线索：{content}")\n            except Exception as exc:\n                descriptions.append(f"第{index}张图片识别失败：{exc}")\n\n        return descriptions\n'
EMOTE_PICKER = '\n    def _pick_collected_emote_for_reply(self, chat_id: str) -> dict[str, Any] | None:\n        """从当前群收集到的表情里挑一个，尽量避免总发同一个。"""\n        self._ensure_emote_pool_loaded()\n        gid = str(chat_id)\n        pool = self._group_emote_pool.get(gid, [])\n        if not isinstance(pool, list) or not pool:\n            return None\n\n        now = datetime.now()\n        valid: list[dict[str, Any]] = []\n\n        try:\n            ttl_hours = float(os.getenv("QQ_EMOTE_POOL_TTL_HOURS", "24"))\n        except Exception:\n            ttl_hours = 24.0\n        ttl_hours = max(1.0, min(ttl_hours, 168.0))\n\n        for item in pool:\n            if not isinstance(item, dict):\n                continue\n            emote_type = str(item.get("type", "") or "")\n            if emote_type not in {"face", "image"}:\n                continue\n\n            # 图片 URL/rkey 可能过期；face 可以长期用。\n            if emote_type == "image":\n                seen_at = item.get("last_seen_at") or item.get("first_seen_at")\n                if seen_at:\n                    try:\n                        dt = datetime.fromisoformat(str(seen_at))\n                        if (now - dt).total_seconds() > ttl_hours * 3600:\n                            continue\n                    except Exception:\n                        pass\n\n            key = str(item.get("key", "") or "")\n            if not key:\n                continue\n\n            valid.append(item)\n\n        if not valid:\n            return None\n\n        if not hasattr(self, "_recent_sent_emote_keys"):\n            self._recent_sent_emote_keys = {}\n\n        recent_keys = self._recent_sent_emote_keys.setdefault(gid, [])\n        if not isinstance(recent_keys, list):\n            recent_keys = []\n            self._recent_sent_emote_keys[gid] = recent_keys\n\n        try:\n            avoid_n = int(os.getenv("QQ_EMOTE_AVOID_RECENT_N", "8"))\n        except Exception:\n            avoid_n = 8\n        avoid_n = max(2, min(avoid_n, 30))\n        avoid = set(str(x) for x in recent_keys[-avoid_n:])\n\n        candidates = [item for item in valid if str(item.get("key", "")) not in avoid]\n        if len(candidates) < max(2, min(5, len(valid) // 3)):\n            candidates = valid\n\n        weights: list[float] = []\n        for item in candidates:\n            key = str(item.get("key", "") or "")\n            try:\n                use_count = int(item.get("use_count", 0) or 0)\n            except Exception:\n                use_count = 0\n\n            weight = 1.0 / (1.0 + 0.65 * use_count)\n\n            # 最近发过的强烈降权，但不是绝对不能发，避免池子太小发不出来。\n            if key in avoid:\n                weight *= 0.18\n\n            # 动画/图片表情略微加权，内置 face 稍微降一点，避免总是普通黄脸。\n            if str(item.get("type", "")) == "image":\n                weight *= 1.15\n            else:\n                weight *= 0.85\n\n            # 加一点随机扰动，避免排序固定。\n            try:\n                weight *= random.uniform(0.75, 1.35)\n            except Exception:\n                pass\n\n            weights.append(max(0.01, weight))\n\n        try:\n            picked = random.choices(candidates, weights=weights, k=1)[0]\n        except Exception:\n            try:\n                picked = random.choice(candidates)\n            except Exception:\n                picked = candidates[-1]\n\n        key = str(picked.get("key", "") or "")\n        if key:\n            recent_keys.append(key)\n            self._recent_sent_emote_keys[gid] = recent_keys[-max(avoid_n * 2, 20):]\n\n        return picked\n'


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


def ensure_methods(src: str, block: str, names: list[str], before_method: str) -> str:
    for name in names:
        method_text = extract_one_method(block, name)
        if method_range(src, name) is not None:
            src = replace_method(src, name, method_text)
        else:
            target = before_method if method_range(src, before_method) else "_handle_message"
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


def patch_send_via_gateway(src: str) -> str:
    if "允许只有 @，不会拦截" in src and "_maybe_send_leading_at_as_segment" in src:
        return src

    if method_range(src, "_send_via_gateway") is None:
        print("⚠️ 找不到 _send_via_gateway，无法修复普通回复 @ 转消息段。")
        return src

    return insert_after_docstring(src, "_send_via_gateway", SEND_AT_SNIPPET)


def main() -> None:
    if not TARGET.exists():
        raise SystemExit(f"找不到文件：{TARGET}")

    src = TARGET.read_text(encoding="utf-8")
    backup = TARGET.with_suffix(".py.bak_at_vision_emote_variety")
    backup.write_text(src, encoding="utf-8")

    # 1. 只 @ 也要真正 @ 上。
    src = ensure_methods(
        src,
        AT_HELPERS,
        [
            "_parse_leading_numeric_at_reply",
            "_send_group_at_text_segments_generic",
            "_maybe_send_leading_at_as_segment",
        ],
        "_send_via_gateway",
    )
    src = patch_send_via_gateway(src)

    # 2. 识图结果可见日志，方便确认有没有提取图片文字。
    src = ensure_methods(
        src,
        VISION_HELPERS,
        [
            "_extract_obvious_text_from_image_descriptions",
            "_summarize_image_vision_for_log",
            "_log_system_debug",
            "_log_image_vision_debug",
        ],
        "_start_image_observation_job" if method_range(src, "_start_image_observation_job") else "_handle_message",
    )

    if method_range(src, "_start_image_observation_job") is not None:
        src = replace_method(src, "_start_image_observation_job", START_IMAGE_JOB)
    else:
        src = insert_before(src, "_handle_message", START_IMAGE_JOB)

    if method_range(src, "_describe_images_with_qwen_vl") is not None:
        src = replace_method(src, "_describe_images_with_qwen_vl", VISION_DESCRIBE)
    else:
        print("⚠️ 没找到 _describe_images_with_qwen_vl，已跳过识图 prompt 更新。")

    # 3. 表情包选择去单一化。
    if method_range(src, "_pick_collected_emote_for_reply") is not None:
        src = replace_method(src, "_pick_collected_emote_for_reply", EMOTE_PICKER)
    else:
        print("⚠️ 没找到 _pick_collected_emote_for_reply，说明你可能还没启用表情池补丁；已跳过去单一化。")

    compile(src, str(TARGET), "exec")
    TARGET.write_text(src, encoding="utf-8")

    print("✅ 已修复：只 @ 也真正 @ 上 + 识图日志 + 表情包选择多样化")
    print("1. 模型只输出 @QQ 时，会发送真正 OneBot at 段，不再拦截。")
    print("2. 图片识图完成后会输出 [QQVision] 日志，能看到文字=... / 清晰度=... / 内容=...")
    print("3. 回复附带表情包时会避开最近发过的表情，并按 use_count 降权，减少总发同一个。")
    print(f"备份文件：{backup}")
    print("下一步：")
    print("  python -m py_compile .\\src\\clawmini\\tools\\qq_auto_reply.py")
    print("  python app.py")
    print()
    print("可调参数：")
    print('  $env:QQ_EMOTE_AVOID_RECENT_N="8"')
    print('  $env:QQ_EMOTE_POOL_TTL_HOURS="24"')


if __name__ == "__main__":
    main()
