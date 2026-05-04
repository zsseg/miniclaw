#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import ast
from pathlib import Path


PROJECT_ROOT = Path.cwd()
TARGET = PROJECT_ROOT / "src" / "clawmini" / "tools" / "qq_auto_reply.py"

SEGMENT_HELPER = '\n    def _send_group_at_text_via_napcat_segments(self, chat_id: str, target_qq: str, text: str) -> ToolResult:\n        """用 OneBot 消息段发送群聊 @ + 文本。\n\n        不走 raw CQ 字符串，避免 [CQ:at,qq=xxx] 被当普通文本显示。\n        """\n        plain_text = self._sanitize_reply_before_send(text)\n        if not plain_text:\n            return ToolResult(False, "戳一戳回复为空或被安全过滤，已阻止发送。")\n\n        group_id = str(chat_id or "").strip()\n        qq = str(target_qq or "").strip()\n        if not group_id or not qq:\n            return self._send_via_gateway(chat_id=chat_id, reply=plain_text, message_type="group")\n\n        if self.gateway_mode == "managed":\n            self._refresh_managed_gateway_config()\n\n        base_candidates: list[str] = []\n        for raw_base in (\n            str(getattr(self.gateway, "api_base_url", "") or "").strip(),\n            str(getattr(self, "managed_api_base_url", "") or "").strip(),\n        ):\n            if not raw_base:\n                continue\n            base = raw_base.rstrip("/")\n            if base and base not in base_candidates:\n                base_candidates.append(base)\n            # 如果拿到的是 NapCat 插件页地址，顺便尝试根路径。\n            if "/plugin/" in base:\n                root = base.split("/plugin/", 1)[0].rstrip("/")\n                if root and root not in base_candidates:\n                    base_candidates.append(root)\n\n        token = (\n            str(getattr(self.gateway, "access_token", "") or "").strip()\n            or str(getattr(self, "managed_access_token", "") or "").strip()\n        )\n\n        payload = {\n            "group_id": int(group_id) if group_id.isdigit() else group_id,\n            "message": [\n                {"type": "at", "data": {"qq": int(qq) if qq.isdigit() else qq}},\n                {"type": "text", "data": {"text": " " + plain_text}},\n            ],\n            "auto_escape": False,\n        }\n\n        last_error = ""\n        for base in base_candidates:\n            endpoint = base.rstrip("/") + "/send_group_msg"\n            headers = {"Content-Type": "application/json"}\n            if token:\n                headers["Authorization"] = f"Bearer {token}"\n\n            req = urllib.request.Request(\n                endpoint,\n                data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),\n                headers=headers,\n                method="POST",\n            )\n\n            try:\n                with urllib.request.urlopen(req, timeout=12) as resp:\n                    raw = resp.read().decode("utf-8", errors="replace")\n                try:\n                    body = json.loads(raw)\n                except Exception:\n                    body = {"raw": raw}\n\n                ok = True\n                if isinstance(body, dict):\n                    if str(body.get("status", "")).lower() == "failed":\n                        ok = False\n                    if "retcode" in body:\n                        try:\n                            ok = int(body.get("retcode")) == 0\n                        except Exception:\n                            ok = False\n\n                meta = {\n                    "chat_id": chat_id,\n                    "message_type": "group",\n                    "reply": f"@{qq} {plain_text}",\n                    "plain_reply": plain_text,\n                    "at_qq": qq,\n                    "endpoint": endpoint,\n                    "segment_message": True,\n                    "response": raw,\n                    "parsed_response": body,\n                }\n                if ok:\n                    return ToolResult(True, "ok", meta)\n\n                last_error = f"{endpoint} 返回失败：{raw[:500]}"\n\n            except Exception as exc:\n                last_error = f"{endpoint} 请求失败：{exc}"\n\n        # 兜底：不要再发 [CQ:at,...]，否则又会显示源码。直接发普通文本。\n        fallback = self._send_via_gateway(chat_id=chat_id, reply=plain_text, message_type="group")\n        if fallback.success:\n            meta = dict(fallback.meta) if isinstance(fallback.meta, dict) else {}\n            meta["reply"] = plain_text\n            meta["at_fallback_failed"] = last_error\n            return ToolResult(True, "ok（@消息段失败，已退回普通文本）", meta)\n\n        if last_error:\n            return ToolResult(False, f"戳一戳@消息段发送失败：{last_error}")\n        return fallback\n'
HANDLE_POKE = '\n    def _handle_poke_notice(self, payload: dict[str, Any]) -> ToolResult:\n        """处理戳一戳 notice。群聊回应时用消息段 @ 戳的人。"""\n        if not self.enabled or self.paused:\n            return ToolResult(True, "戳一戳已收到，但自动回复已禁用或处于安静模式。", {"poke": True})\n\n        if not self._poke_targets_self(payload):\n            return ToolResult(True, "戳一戳目标不是我，已忽略。", {"poke": True, "ignored": "target_not_self"})\n\n        group_id = str(payload.get("group_id", "") or "").strip()\n        sender_id = self._extract_poke_sender_id(payload)\n        self_id = str(payload.get("self_id", "") or "").strip()\n\n        if sender_id and self_id and sender_id == self_id:\n            return ToolResult(True, "已忽略机器人自己的戳一戳。", {"poke": True, "ignored": "self"})\n\n        if group_id:\n            source = "group"\n            chat_id = group_id\n            if chat_id not in self.target_group_ids:\n                return ToolResult(True, "非目标群戳一戳，已忽略。", {"poke": True, "ignored": "non_target_group"})\n        else:\n            source = "private"\n            chat_id = sender_id or str(payload.get("user_id", "") or "").strip()\n            if not chat_id:\n                return ToolResult(True, "戳一戳缺少私聊 user_id，已忽略。", {"poke": True, "ignored": "missing_chat_id"})\n            if not self.private_enabled:\n                return ToolResult(True, "私聊自动回复未启用，戳一戳已忽略。", {"poke": True, "ignored": "private_disabled"})\n\n        cooldown_hit, cooldown_reason = self._poke_cooldown_hit(chat_id, sender_id or "anon")\n        if cooldown_hit:\n            return ToolResult(True, cooldown_reason, {"poke": True, "cooldown": True})\n\n        plain_reply = self._build_poke_reply(payload, source, sender_id)\n\n        if source == "group" and sender_id:\n            send_result = self._send_group_at_text_via_napcat_segments(\n                chat_id=chat_id,\n                target_qq=sender_id,\n                text=plain_reply,\n            )\n            log_reply = f"@{sender_id} {plain_reply}"\n        else:\n            send_result = self._send_via_gateway(chat_id=chat_id, reply=plain_reply, message_type=source)\n            log_reply = plain_reply\n\n        if not send_result.success:\n            return send_result\n\n        self.last_auto_reply[chat_id] = datetime.now()\n\n        input_text = f"[戳一戳] {sender_id or \'有人\'} 戳了我一下"\n        safe_sender = f"user_{abs(hash(sender_id or \'poke\')) % 10000}"\n        context_info = {\n            "source": source,\n            "chat_id": chat_id,\n            "sender_id": sender_id,\n            "notice_type": str(payload.get("notice_type", "")),\n            "sub_type": str(payload.get("sub_type", "")),\n            "poke": True,\n        }\n\n        self._append_log(chat_id, safe_sender, input_text, log_reply)\n        self._remember_recent_exchange(chat_id, source, sender_id or "poke", input_text, log_reply, context_info)\n\n        meta = dict(send_result.meta) if isinstance(send_result.meta, dict) else {}\n        meta.update(\n            {\n                "poke": True,\n                "chat_id": chat_id,\n                "message_type": source,\n                "reply": log_reply,\n                "reply_parts": [log_reply],\n                "reply_count": 1,\n                "sender_id": sender_id,\n                "notice_type": str(payload.get("notice_type", "")),\n                "sub_type": str(payload.get("sub_type", "")),\n            }\n        )\n        return ToolResult(True, f"已回应戳一戳到 {source}/{chat_id}: {log_reply}", meta)\n'


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


def ensure_method(src: str, method_name: str, method_text: str, before_method: str) -> str:
    if method_range(src, method_name) is not None:
        return replace_method(src, method_name, method_text)
    return insert_before(src, before_method, method_text)


def main() -> None:
    if not TARGET.exists():
        raise SystemExit(f"找不到文件：{TARGET}")

    src = TARGET.read_text(encoding="utf-8")
    backup = TARGET.with_suffix(".py.bak_poke_at_segment")
    backup.write_text(src, encoding="utf-8")

    src = ensure_method(
        src,
        "_send_group_at_text_via_napcat_segments",
        SEGMENT_HELPER,
        "_handle_poke_notice" if method_range(src, "_handle_poke_notice") else "_send_via_gateway",
    )

    if method_range(src, "_handle_poke_notice") is None:
        raise RuntimeError("没找到 _handle_poke_notice。请先运行戳一戳补丁，或者把 qq_auto_reply.py 发我。")

    src = replace_method(src, "_handle_poke_notice", HANDLE_POKE)

    compile(src, str(TARGET), "exec")
    TARGET.write_text(src, encoding="utf-8")

    print("✅ 已修复戳一戳 @ 显示成 CQ 源码的问题")
    print("现在群聊戳一戳会用 OneBot 消息段发送：at 段 + text 段。")
    print("如果消息段接口失败，会退回普通文本，但不会再发送 [CQ:at,qq=...] 源码。")
    print(f"备份文件：{backup}")
    print("下一步：")
    print("  python -m py_compile .\\src\\clawmini\\tools\\qq_auto_reply.py")
    print("  python app.py")


if __name__ == "__main__":
    main()
