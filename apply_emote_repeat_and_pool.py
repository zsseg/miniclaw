#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import ast
from pathlib import Path


PROJECT_ROOT = Path.cwd()
TARGET = PROJECT_ROOT / "src" / "clawmini" / "tools" / "qq_auto_reply.py"

EMOTE_HELPERS = '\n    def _cq_param_dict(self, param_text: str) -> dict[str, str]:\n        """解析 CQ 码参数。"""\n        try:\n            import html as _html\n        except Exception:\n            _html = None\n\n        params: dict[str, str] = {}\n        for part in str(param_text or "").split(","):\n            if "=" not in part:\n                continue\n            key, value = part.split("=", 1)\n            key = key.strip()\n            value = value.strip()\n            if _html is not None:\n                try:\n                    value = _html.unescape(value)\n                except Exception:\n                    pass\n            if key:\n                params[key] = value\n        return params\n\n    def _extract_emote_items_from_text(self, text: str) -> list[dict[str, Any]]:\n        """从 CQ 消息里提取可复读/可收藏的表情项。\n\n        支持：\n        - [CQ:face,id=...]\n        - [CQ:image,...]，包括动画表情/表情包图片\n        """\n        raw = str(text or "")\n        items: list[dict[str, Any]] = []\n\n        for match in re.finditer(r"\\[CQ:(face|image),([^\\]]*)\\]", raw, flags=re.I):\n            cq_type = match.group(1).lower()\n            params = self._cq_param_dict(match.group(2))\n\n            if cq_type == "face":\n                face_id = str(params.get("id", "") or "").strip()\n                if not face_id:\n                    continue\n                items.append(\n                    {\n                        "type": "face",\n                        "key": f"face:{face_id}",\n                        "data": {"id": int(face_id) if face_id.isdigit() else face_id},\n                        "summary": f"[表情:{face_id}]",\n                    }\n                )\n                continue\n\n            if cq_type == "image":\n                file_value = str(params.get("file", "") or "").strip()\n                url_value = str(params.get("url", "") or "").strip()\n                summary = str(params.get("summary", "") or "").strip()\n                sub_type = str(params.get("sub_type", "") or "").strip()\n\n                # 表情包/动画表情一般有 summary=[动画表情] 或 sub_type=1。\n                is_sticker = ("动画表情" in summary) or sub_type == "1" or "emoji" in file_value.lower()\n\n                send_file = url_value or file_value\n                if not send_file:\n                    continue\n\n                key_seed = file_value or url_value\n                key = f"image:{key_seed}"\n                items.append(\n                    {\n                        "type": "image",\n                        "key": key,\n                        "data": {"file": send_file},\n                        "file": file_value,\n                        "url": url_value,\n                        "summary": summary or ("[动画表情]" if is_sticker else "[图片]"),\n                        "sub_type": sub_type,\n                        "is_sticker": bool(is_sticker),\n                    }\n                )\n\n        return items\n\n    def _emote_pool_path(self):\n        try:\n            from pathlib import Path as _Path\n            root = getattr(self, "workspace_dir", None)\n            if root:\n                return _Path(root) / "qq_emote_pool.json"\n            return _Path.cwd() / "qq_emote_pool.json"\n        except Exception:\n            return None\n\n    def _ensure_emote_pool_loaded(self) -> None:\n        if hasattr(self, "_group_emote_pool") and isinstance(self._group_emote_pool, dict):\n            return\n\n        self._group_emote_pool = {}\n        path = self._emote_pool_path()\n        if not path:\n            return\n\n        try:\n            if path.exists():\n                data = json.loads(path.read_text(encoding="utf-8"))\n                if isinstance(data, dict):\n                    self._group_emote_pool = data\n        except Exception:\n            self._group_emote_pool = {}\n\n    def _save_emote_pool(self) -> None:\n        path = self._emote_pool_path()\n        if not path:\n            return\n\n        try:\n            path.parent.mkdir(parents=True, exist_ok=True)\n            path.write_text(json.dumps(self._group_emote_pool, ensure_ascii=False, indent=2), encoding="utf-8")\n        except Exception:\n            pass\n\n    def _remember_emotes_from_message(self, chat_id: str, sender_id: str, text: str) -> None:\n        """收藏群友发过的表情包/表情，供以后复读或回复时偶尔发送。"""\n        items = self._extract_emote_items_from_text(text)\n        if not items:\n            return\n\n        self._ensure_emote_pool_loaded()\n\n        gid = str(chat_id or "").strip()\n        if not gid:\n            return\n\n        try:\n            max_pool = int(os.getenv("QQ_EMOTE_POOL_MAX", "120"))\n        except Exception:\n            max_pool = 120\n        max_pool = max(20, min(max_pool, 500))\n\n        try:\n            ttl_hours = float(os.getenv("QQ_EMOTE_POOL_TTL_HOURS", "24"))\n        except Exception:\n            ttl_hours = 24.0\n        ttl_hours = max(1.0, min(ttl_hours, 168.0))\n\n        now = datetime.now()\n        now_s = now.isoformat(timespec="seconds")\n\n        pool = self._group_emote_pool.setdefault(gid, [])\n        if not isinstance(pool, list):\n            pool = []\n            self._group_emote_pool[gid] = pool\n\n        # 清理过期 URL 图片；QQ 图片 URL/rkey 可能会过期，不建议永久保留。\n        cleaned: list[dict[str, Any]] = []\n        for old in pool:\n            if not isinstance(old, dict):\n                continue\n            seen_at = old.get("last_seen_at") or old.get("seen_at")\n            keep = True\n            if seen_at:\n                try:\n                    dt = datetime.fromisoformat(str(seen_at))\n                    if (now - dt).total_seconds() > ttl_hours * 3600:\n                        keep = False\n                except Exception:\n                    keep = True\n            if keep:\n                cleaned.append(old)\n        pool[:] = cleaned\n\n        for item in items:\n            key = str(item.get("key", "") or "")\n            if not key:\n                continue\n\n            existing = None\n            for old in pool:\n                if isinstance(old, dict) and old.get("key") == key:\n                    existing = old\n                    break\n\n            record = {\n                **item,\n                "key": key,\n                "sender_id": str(sender_id or ""),\n                "first_seen_at": now_s,\n                "last_seen_at": now_s,\n                "use_count": 0,\n            }\n\n            if existing:\n                existing.update({k: v for k, v in record.items() if k != "first_seen_at"})\n                existing["last_seen_at"] = now_s\n            else:\n                pool.append(record)\n\n        pool[:] = pool[-max_pool:]\n        self._save_emote_pool()\n\n    def _send_group_segments_via_napcat(self, chat_id: str, segments: list[dict[str, Any]]) -> ToolResult:\n        """直接用 OneBot 消息段发送群消息，避免 CQ 码被当纯文本显示。"""\n        group_id = str(chat_id or "").strip()\n        if not group_id or not segments:\n            return ToolResult(False, "缺少群号或消息段。")\n\n        if getattr(self, "gateway_mode", "") == "managed":\n            try:\n                self._refresh_managed_gateway_config()\n            except Exception:\n                pass\n\n        base_candidates: list[str] = []\n        for raw_base in (\n            str(getattr(getattr(self, "gateway", None), "api_base_url", "") or "").strip(),\n            str(getattr(self, "managed_api_base_url", "") or "").strip(),\n        ):\n            if not raw_base:\n                continue\n            base = raw_base.rstrip("/")\n            if base and base not in base_candidates:\n                base_candidates.append(base)\n            if "/plugin/" in base:\n                root = base.split("/plugin/", 1)[0].rstrip("/")\n                if root and root not in base_candidates:\n                    base_candidates.append(root)\n\n        if not base_candidates:\n            return ToolResult(False, "没有可用 NapCat API 地址，无法发送消息段。")\n\n        token = (\n            str(getattr(getattr(self, "gateway", None), "access_token", "") or "").strip()\n            or str(getattr(self, "managed_access_token", "") or "").strip()\n        )\n\n        payload = {\n            "group_id": int(group_id) if group_id.isdigit() else group_id,\n            "message": segments,\n            "auto_escape": False,\n        }\n\n        last_error = ""\n        for base in base_candidates:\n            endpoint = base.rstrip("/") + "/send_group_msg"\n            headers = {"Content-Type": "application/json"}\n            if token:\n                headers["Authorization"] = f"Bearer {token}"\n\n            req = urllib.request.Request(\n                endpoint,\n                data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),\n                headers=headers,\n                method="POST",\n            )\n\n            try:\n                with urllib.request.urlopen(req, timeout=15) as resp:\n                    raw = resp.read().decode("utf-8", errors="replace")\n\n                try:\n                    body = json.loads(raw)\n                except Exception:\n                    body = {"raw": raw}\n\n                ok = True\n                if isinstance(body, dict):\n                    if str(body.get("status", "")).lower() == "failed":\n                        ok = False\n                    if "retcode" in body:\n                        try:\n                            ok = int(body.get("retcode")) == 0\n                        except Exception:\n                            ok = False\n\n                if ok:\n                    return ToolResult(\n                        True,\n                        "ok",\n                        {\n                            "chat_id": chat_id,\n                            "message_type": "group",\n                            "segments": segments,\n                            "segment_message": True,\n                            "endpoint": endpoint,\n                            "response": raw,\n                            "parsed_response": body,\n                        },\n                    )\n\n                last_error = f"{endpoint} 返回失败：{raw[:500]}"\n            except Exception as exc:\n                last_error = f"{endpoint} 请求失败：{exc}"\n\n        return ToolResult(False, last_error or "消息段发送失败。")\n\n    def _send_emote_item_to_group(self, chat_id: str, item: dict[str, Any]) -> ToolResult:\n        """发送收藏的表情项。失败时不退回 CQ 字符串，避免源码刷屏。"""\n        if not isinstance(item, dict):\n            return ToolResult(False, "无效表情项。")\n\n        emote_type = str(item.get("type", "") or "")\n        data = item.get("data", {})\n        if not isinstance(data, dict):\n            data = {}\n\n        if emote_type == "face":\n            face_id = data.get("id")\n            if face_id in (None, ""):\n                return ToolResult(False, "表情缺少 id。")\n            seg = {"type": "face", "data": {"id": int(face_id) if str(face_id).isdigit() else face_id}}\n            return self._send_group_segments_via_napcat(chat_id, [seg])\n\n        if emote_type == "image":\n            file_value = str(data.get("file", "") or item.get("url", "") or item.get("file", "") or "").strip()\n            if not file_value:\n                return ToolResult(False, "图片表情缺少 file/url。")\n            seg = {"type": "image", "data": {"file": file_value}}\n            return self._send_group_segments_via_napcat(chat_id, [seg])\n\n        return ToolResult(False, f"未知表情类型：{emote_type}")\n\n    def _normalize_emote_repeat_keys(self, text: str) -> list[str]:\n        items = self._extract_emote_items_from_text(text)\n        keys: list[str] = []\n        for item in items:\n            key = str(item.get("key", "") or "")\n            if key:\n                keys.append(key)\n        return keys\n\n    def _recent_emote_repeat_stats(self, chat_id: str, current_sender_id: str, current_text: str) -> dict[str, Any]:\n        """统计最近是否多人复读同一个表情/表情包。"""\n        current_items = self._extract_emote_items_from_text(current_text)\n        if not current_items:\n            return {"item": None, "key": "", "count": 0, "user_count": 0, "users": set()}\n\n        current_key = str(current_items[0].get("key", "") or "")\n        if not current_key:\n            return {"item": None, "key": "", "count": 0, "user_count": 0, "users": set()}\n\n        users: set[str] = set()\n        count = 0\n\n        def consider(sender_id: str, text: str) -> None:\n            nonlocal count, users\n            keys = self._normalize_emote_repeat_keys(text)\n            if current_key in keys:\n                count += 1\n                if sender_id:\n                    users.add(str(sender_id))\n\n        consider(str(current_sender_id or ""), current_text)\n\n        try:\n            batch = self.pending_group_batches.get(str(chat_id), {})\n            if isinstance(batch, dict):\n                for item in batch.get("messages", [])[-16:]:\n                    if not isinstance(item, dict):\n                        continue\n                    consider(str(item.get("sender_id", "") or ""), str(item.get("text", "") or ""))\n        except Exception:\n            pass\n\n        try:\n            for item in self.recent_messages.get(str(chat_id), [])[-24:]:\n                if not isinstance(item, dict):\n                    continue\n                sid = str(item.get("sender_id", "") or "")\n                if sid in {"SELF", "BOT", "ME", "group_batch", "proactive_topic"}:\n                    continue\n                consider(sid, str(item.get("text", "") or ""))\n        except Exception:\n            pass\n\n        return {\n            "item": current_items[0],\n            "key": current_key,\n            "count": count,\n            "user_count": len(users),\n            "users": users,\n        }\n\n    def _should_join_emote_repeat(\n        self,\n        chat_id: str,\n        sender_id: str,\n        text: str,\n        context_info: dict[str, Any] | None = None,\n    ) -> tuple[bool, dict[str, Any] | None, str]:\n        """大家复读表情包/表情时，机器人偶尔参与一次。"""\n        context_info = context_info or {}\n\n        if context_info.get("mentioned") or context_info.get("explicit_self"):\n            return False, None, ""\n\n        stats = self._recent_emote_repeat_stats(chat_id, sender_id, text)\n        item = stats.get("item")\n        key = str(stats.get("key", "") or "")\n        count = int(stats.get("count", 0) or 0)\n        user_count = int(stats.get("user_count", 0) or 0)\n\n        if not item or not key:\n            return False, None, ""\n\n        # 至少两个人参与同一个表情复读，bot 才跟。\n        if not (user_count >= 2 and count >= 2):\n            return False, None, ""\n\n        if not hasattr(self, "_last_emote_repeat_join"):\n            self._last_emote_repeat_join = {}\n\n        try:\n            cooldown = float(os.getenv("QQ_EMOTE_REPEAT_COOLDOWN_SEC", "75"))\n        except Exception:\n            cooldown = 75.0\n        cooldown = max(20.0, min(cooldown, 240.0))\n\n        now = datetime.now()\n        cooldown_key = f"{chat_id}:{key}"\n        last = self._last_emote_repeat_join.get(cooldown_key)\n        if isinstance(last, datetime) and (now - last).total_seconds() < cooldown:\n            return False, None, ""\n\n        self._last_emote_repeat_join[cooldown_key] = now\n        return True, item, f"检测到多人复读同一个表情/表情包：{item.get(\'summary\', key)}"\n\n    def _maybe_send_group_emote_repeat(\n        self,\n        chat_id: str,\n        sender_id: str,\n        text: str,\n        context_info: dict[str, Any] | None = None,\n    ) -> ToolResult | None:\n        """如果当前消息触发表情包复读，直接用消息段跟一次。"""\n        context_info = context_info or {}\n\n        try:\n            self._remember_emotes_from_message(chat_id, sender_id, text)\n        except Exception:\n            pass\n\n        try:\n            ok, item, reason = self._should_join_emote_repeat(chat_id, sender_id, text, context_info)\n        except Exception:\n            return None\n\n        if not ok or not item:\n            return None\n\n        send_result = self._send_emote_item_to_group(chat_id, item)\n        if not send_result.success:\n            return None\n\n        now = datetime.now()\n        self.last_auto_reply[chat_id] = now\n\n        input_text = f"[表情包复读] {sender_id or \'有人\'} 发了 {item.get(\'summary\', item.get(\'key\', \'表情\'))}"\n        reply_label = f"[已复读表情包] {item.get(\'summary\', item.get(\'key\', \'表情\'))}"\n\n        safe_sender = f"user_{abs(hash(sender_id or \'emote\')) % 10000}"\n        self._append_log(chat_id, safe_sender, input_text, reply_label)\n\n        remember_context = {\n            "source": "group",\n            "chat_id": chat_id,\n            "sender_id": sender_id,\n            "emote_repeat": True,\n            "emote_key": item.get("key", ""),\n        }\n        self._remember_recent_exchange(chat_id, "group", sender_id or "emote", input_text, reply_label, remember_context)\n\n        meta = dict(send_result.meta) if isinstance(send_result.meta, dict) else {}\n        meta.update(\n            {\n                "emote_repeat": True,\n                "chat_id": chat_id,\n                "message_type": "group",\n                "reply": reply_label,\n                "reply_parts": [reply_label],\n                "reply_count": 1,\n                "sender_id": sender_id,\n                "emote_key": item.get("key", ""),\n                "reason": reason,\n            }\n        )\n        return ToolResult(True, f"已参与表情包复读：{reason}", meta)\n\n    def _pick_collected_emote_for_reply(self, chat_id: str) -> dict[str, Any] | None:\n        """从当前群收集到的表情里挑一个可发送的。"""\n        self._ensure_emote_pool_loaded()\n        pool = self._group_emote_pool.get(str(chat_id), [])\n        if not isinstance(pool, list) or not pool:\n            return None\n\n        now = datetime.now()\n        valid: list[dict[str, Any]] = []\n        try:\n            ttl_hours = float(os.getenv("QQ_EMOTE_POOL_TTL_HOURS", "24"))\n        except Exception:\n            ttl_hours = 24.0\n\n        for item in pool:\n            if not isinstance(item, dict):\n                continue\n            if str(item.get("type", "")) not in {"face", "image"}:\n                continue\n\n            # 图片 URL 可能过期，太旧就少用；face 不受影响。\n            if str(item.get("type", "")) == "image":\n                seen_at = item.get("last_seen_at") or item.get("first_seen_at")\n                if seen_at:\n                    try:\n                        dt = datetime.fromisoformat(str(seen_at))\n                        if (now - dt).total_seconds() > ttl_hours * 3600:\n                            continue\n                    except Exception:\n                        pass\n            valid.append(item)\n\n        if not valid:\n            return None\n\n        try:\n            return random.choice(valid[-60:])\n        except Exception:\n            return valid[-1]\n\n    def _maybe_send_collected_emote_after_reply(self, chat_id: str, reply: str = "", message_type: str = "group") -> None:\n        """普通文本回复后，按概率补一个群友发过的表情包/表情。"""\n        if str(message_type or "") != "group":\n            return\n\n        if not str(chat_id or "").strip():\n            return\n\n        # 不给空回复、系统兜底、纯短复读再追加表情，避免显得烦。\n        text = str(reply or "").strip()\n        if not text:\n            return\n        if hasattr(self, "_is_generic_api_fallback_reply") and self._is_generic_api_fallback_reply(text):\n            return\n        if text.startswith("[已复读表情包]"):\n            return\n        if "[CQ:" in text:\n            return\n\n        try:\n            prob = float(os.getenv("QQ_REPLY_EMOTE_PROB", "0.12"))\n        except Exception:\n            prob = 0.12\n        prob = max(0.0, min(prob, 0.8))\n        if prob <= 0:\n            return\n\n        try:\n            if random.random() >= prob:\n                return\n        except Exception:\n            return\n\n        if not hasattr(self, "_last_reply_emote_sent"):\n            self._last_reply_emote_sent = {}\n\n        try:\n            cooldown = float(os.getenv("QQ_REPLY_EMOTE_COOLDOWN_SEC", "100"))\n        except Exception:\n            cooldown = 100.0\n        cooldown = max(20.0, min(cooldown, 600.0))\n\n        now = datetime.now()\n        last = self._last_reply_emote_sent.get(str(chat_id))\n        if isinstance(last, datetime) and (now - last).total_seconds() < cooldown:\n            return\n\n        item = self._pick_collected_emote_for_reply(chat_id)\n        if not item:\n            return\n\n        send_result = self._send_emote_item_to_group(chat_id, item)\n        if not send_result.success:\n            return\n\n        self._last_reply_emote_sent[str(chat_id)] = now\n\n        try:\n            item["use_count"] = int(item.get("use_count", 0) or 0) + 1\n            item["last_used_at"] = now.isoformat(timespec="seconds")\n            self._save_emote_pool()\n        except Exception:\n            pass\n\n        try:\n            reply_label = f"[附带表情包] {item.get(\'summary\', item.get(\'key\', \'表情\'))}"\n            self._append_log(str(chat_id), "emote_after_reply", "[回复后附带表情包]", reply_label)\n            self._remember_recent_exchange(\n                str(chat_id),\n                "group",\n                "emote_after_reply",\n                "[回复后附带表情包]",\n                reply_label,\n                {"source": "group", "chat_id": str(chat_id), "emote_after_reply": True, "emote_key": item.get("key", "")},\n            )\n        except Exception:\n            pass\n'
SEND_WRAPPER = '\n    def _send_via_gateway(self, *args: Any, **kwargs: Any) -> ToolResult:\n        """文本发送网关包装。\n\n        先调用原文本发送逻辑；普通群聊文本成功后，按概率补发一个收集到的表情包。\n        """\n        result = self._send_via_gateway_text_only(*args, **kwargs)\n\n        try:\n            chat_id = kwargs.get("chat_id")\n            reply = kwargs.get("reply")\n            message_type = kwargs.get("message_type")\n\n            if chat_id is None and len(args) >= 1:\n                chat_id = args[0]\n            if reply is None and len(args) >= 2:\n                reply = args[1]\n            if message_type is None and len(args) >= 3:\n                message_type = args[2]\n\n            if getattr(result, "success", False):\n                self._maybe_send_collected_emote_after_reply(\n                    chat_id=str(chat_id or ""),\n                    reply=str(reply or ""),\n                    message_type=str(message_type or ""),\n                )\n        except Exception:\n            pass\n\n        return result\n'


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


def ensure_emote_helpers(src: str) -> str:
    names = [
        "_cq_param_dict",
        "_extract_emote_items_from_text",
        "_emote_pool_path",
        "_ensure_emote_pool_loaded",
        "_save_emote_pool",
        "_remember_emotes_from_message",
        "_send_group_segments_via_napcat",
        "_send_emote_item_to_group",
        "_normalize_emote_repeat_keys",
        "_recent_emote_repeat_stats",
        "_should_join_emote_repeat",
        "_maybe_send_group_emote_repeat",
        "_pick_collected_emote_for_reply",
        "_maybe_send_collected_emote_after_reply",
    ]
    for name in names:
        method_text = extract_one_method(EMOTE_HELPERS, name)
        if method_range(src, name) is not None:
            src = replace_method(src, name, method_text)
        else:
            target = "_handle_message" if method_range(src, "_handle_message") else "_send_via_gateway"
            src = insert_before(src, target, method_text)
    return src


def patch_handle_message_collect(src: str) -> str:
    if "_remember_emotes_from_message(chat_id, sender_id, text)" in src:
        return src

    marker = "        image_refs = self._extract_image_refs(arguments)\n"
    insert = (
        "        if source == \"group\":\n"
        "            try:\n"
        "                self._remember_emotes_from_message(chat_id, sender_id, text)\n"
        "            except Exception:\n"
        "                pass\n"
    )
    if marker in src:
        return src.replace(marker, marker + insert, 1)

    print("⚠️ 没找到 image_refs 插入点，表情池仍会在复读判断时收集，但普通收藏可能不完整。")
    return src


def patch_emote_repeat_before_should_reply(src: str) -> str:
    if "_maybe_send_group_emote_repeat(" in src and "表情包复读：多人复读同一表情时" in src:
        return src

    repeat_guard = (
        "            # 表情包复读：多人复读同一表情时，偶尔跟一次。\n"
        "            try:\n"
        "                emote_repeat_result = self._maybe_send_group_emote_repeat(\n"
        "                    chat_id=chat_id,\n"
        "                    sender_id=sender_id,\n"
        "                    text=text,\n"
        "                    context_info=context_info,\n"
        "                )\n"
        "                if emote_repeat_result is not None:\n"
        "                    return emote_repeat_result\n"
        "            except Exception:\n"
        "                pass\n\n"
    )

    # 插到 group 分支 should_reply 判断前，覆盖 face 表情复读。
    marker = "            should_reply, reply_reason = self._should_reply_to_group_message(\n"
    if marker in src:
        src = src.replace(marker, repeat_guard + marker, 1)
    else:
        print("⚠️ 没找到 should_reply 插入点，尝试只 patch 纯图 guard。")

    # 如果已有纯图片/表情包硬拦截，先尝试复读再返回背景。
    pure_return = '                return ToolResult(True, "纯图片/表情包：已记录为背景并预热识图，不主动回复。")'
    pure_insert = (
        "                try:\n"
        "                    emote_repeat_result = self._maybe_send_group_emote_repeat(\n"
        "                        chat_id=chat_id,\n"
        "                        sender_id=sender_id,\n"
        "                        text=text,\n"
        "                        context_info=context_info,\n"
        "                    )\n"
        "                    if emote_repeat_result is not None:\n"
        "                        return emote_repeat_result\n"
        "                except Exception:\n"
        "                    pass\n"
        + pure_return
    )
    if pure_return in src and pure_insert not in src:
        src = src.replace(pure_return, pure_insert, 1)

    return src


def patch_send_via_gateway_wrapper(src: str) -> str:
    if method_range(src, "_send_via_gateway_text_only") is not None:
        # 已经包过；只更新 wrapper 内容。
        if method_range(src, "_send_via_gateway") is not None:
            src = replace_method(src, "_send_via_gateway", SEND_WRAPPER)
        return src

    rng = method_range(src, "_send_via_gateway")
    if rng is None:
        print("⚠️ 找不到 _send_via_gateway，无法添加回复后表情包概率发送。")
        return src

    start, end = rng
    lines = src.splitlines()

    # 重命名原方法。
    def_line_idx = start - 1
    lines[def_line_idx] = lines[def_line_idx].replace("def _send_via_gateway(", "def _send_via_gateway_text_only(", 1)

    src2 = "\n".join(lines) + "\n"
    src2 = insert_before(src2, "_send_via_gateway_text_only", SEND_WRAPPER)
    return src2


def main() -> None:
    if not TARGET.exists():
        raise SystemExit(f"找不到文件：{TARGET}")

    src = TARGET.read_text(encoding="utf-8")
    backup = TARGET.with_suffix(".py.bak_emote_repeat_pool")
    backup.write_text(src, encoding="utf-8")

    src = ensure_emote_helpers(src)
    src = patch_handle_message_collect(src)
    src = patch_emote_repeat_before_should_reply(src)
    src = patch_send_via_gateway_wrapper(src)

    compile(src, str(TARGET), "exec")
    TARGET.write_text(src, encoding="utf-8")

    print("✅ 已添加：表情包复读 + 回复时偶尔发群友表情包")
    print("1. 多人复读同一个 QQ face / 图片表情包时，bot 会按冷却偶尔跟一次。")
    print("2. bot 会收集群友发过的 face/image 表情，普通回复后按概率补发一个。")
    print("3. 表情/图片发送使用 OneBot 消息段，不发送 raw CQ 源码。")
    print(f"备份文件：{backup}")
    print("下一步：")
    print("  python -m py_compile .\\src\\clawmini\\tools\\qq_auto_reply.py")
    print("  python app.py")
    print()
    print("可调参数：")
    print('  $env:QQ_EMOTE_REPEAT_COOLDOWN_SEC="75"')
    print('  $env:QQ_REPLY_EMOTE_PROB="0.12"')
    print('  $env:QQ_REPLY_EMOTE_COOLDOWN_SEC="100"')
    print('  $env:QQ_EMOTE_POOL_MAX="120"')
    print('  $env:QQ_EMOTE_POOL_TTL_HOURS="24"')


if __name__ == "__main__":
    main()
