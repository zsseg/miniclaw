#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import ast
from pathlib import Path


PROJECT_ROOT = Path.cwd()
QQ_TOOL = PROJECT_ROOT / "src" / "clawmini" / "tools" / "qq_auto_reply.py"
WORKSPACE_APP = PROJECT_ROOT / "src" / "clawmini" / "workspace_app.py"

NEW_POLL_PENDING = '\n    def _poll_pending(self) -> ToolResult:\n        """轮询并执行到期回复任务。\n\n        修复点：\n        - 私聊延迟回复、群聊候选/主动回复发送后，都会写入 qq_auto_reply.log；\n        - 同时通过 meta["sent_replies"] 返回给前端，让 Live Ledger 也能显示。\n        """\n        now = datetime.now()\n        sent_reply_records: list[dict[str, Any]] = []\n\n        # 1) 私聊等待队列\n        due_ids = [cid for cid, item in self.pending_private.items() if item.get("due_at") <= now]\n        sent = 0\n        skipped = 0\n\n        for chat_id in due_ids:\n            item = self.pending_private.pop(chat_id, None)\n            if not item:\n                continue\n\n            if self._is_in_cooldown(chat_id):\n                skipped += 1\n                continue\n\n            sender_id = str(item.get("sender_id", ""))\n            safe_sender = f"user_{abs(hash(sender_id)) % 10000}"\n            text = str(item.get("text", ""))\n\n            context_info = {\n                "source": str(item.get("source", "private")),\n                "chat_id": chat_id,\n                "sender_id": sender_id,\n                "sender_name": str(item.get("sender_name", "")).strip(),\n                "sender_avatar": str(item.get("sender_avatar", "")).strip(),\n                "group_name": str(item.get("group_name", "")).strip(),\n                "group_avatar": str(item.get("group_avatar", "")).strip(),\n                "image_refs": list(item.get("image_refs", [])) if isinstance(item.get("image_refs", []), list) else [],\n                "reply_context": item.get("reply_context", {}),\n            }\n\n            reply_parts = self._build_reply_parts(text, context_info=context_info)\n            if hasattr(self, "_looks_like_no_speech_reply"):\n                reply_parts = [part for part in reply_parts if not self._looks_like_no_speech_reply(part)]\n\n            if not reply_parts:\n                skipped += 1\n                continue\n\n            sent_parts: list[str] = []\n            for part in reply_parts[:2]:\n                send_result = self._send_via_gateway(\n                    chat_id=chat_id,\n                    reply=self._sanitize_reply_before_send(part),\n                    message_type="private",\n                )\n                if not send_result.success:\n                    skipped += 1\n                    break\n\n                meta = send_result.meta if isinstance(send_result.meta, dict) else {}\n                sent_parts.append(str(meta.get("reply", self._sanitize_reply_before_send(part))).strip())\n\n            sent_parts = [part for part in sent_parts if part]\n            if not sent_parts:\n                continue\n\n            self.last_auto_reply[chat_id] = datetime.now()\n            combined_reply = "\\n\\n".join(sent_parts)\n            self._append_log(chat_id, safe_sender, text, combined_reply)\n            self._remember_recent_exchange(chat_id, context_info["source"], sender_id, text, combined_reply, context_info)\n\n            sent_reply_records.append(\n                {\n                    "source": "private",\n                    "message_type": "private",\n                    "chat_id": chat_id,\n                    "sender_id": sender_id,\n                    "sender_name": context_info.get("sender_name", ""),\n                    "input_text": text,\n                    "reply": combined_reply,\n                    "reply_parts": list(sent_parts),\n                    "kind": "private_pending",\n                }\n            )\n            sent += 1\n\n        # 2) 群聊候选/主动回复队列\n        group_sent = 0\n        group_skipped = 0\n        due_group_ids = [\n            cid\n            for cid, item in self.pending_group_batches.items()\n            if item.get("due_at") <= now\n        ]\n\n        for chat_id in due_group_ids:\n            batch = self.pending_group_batches.pop(chat_id, None)\n            if not batch:\n                continue\n\n            messages = batch.get("messages", [])\n            if not isinstance(messages, list) or not messages:\n                group_skipped += 1\n                continue\n\n            if self._is_in_cooldown(chat_id):\n                group_skipped += 1\n                continue\n\n            # 如果消息里已经带了相关度/社交判断字段，就保留守门逻辑；\n            # 如果是旧批次没有这些字段，则不强行丢弃。\n            has_gate_fields = any(\n                isinstance(item, dict)\n                and (\n                    "reply_relevance" in item\n                    or "social_action" in item\n                    or "social_confidence" in item\n                )\n                for item in messages\n            )\n            if has_gate_fields:\n                relevant_messages = [\n                    item for item in messages\n                    if isinstance(item, dict)\n                    and (\n                        int(item.get("reply_relevance", 0) or 0) >= 45\n                        or str(item.get("social_action", "")) in {"reply", "candidate"}\n                    )\n                ]\n                strong_messages = [\n                    item for item in messages\n                    if isinstance(item, dict)\n                    and (\n                        int(item.get("reply_relevance", 0) or 0) >= 70\n                        or (\n                            str(item.get("social_action", "")) == "reply"\n                            and float(item.get("social_confidence", 0.0) or 0.0) >= 0.50\n                        )\n                    )\n                ]\n                if not strong_messages and len(relevant_messages) < 2:\n                    group_skipped += 1\n                    continue\n\n            context_info = batch.get("context_info", {})\n            if not isinstance(context_info, dict):\n                context_info = {}\n\n            context_info = dict(context_info)\n            context_info["source"] = "group"\n            context_info["chat_id"] = chat_id\n            context_info["merge_batch"] = True\n            context_info["batch_messages"] = list(messages)\n\n            batch_text = self._build_group_batch_text(messages)\n            reply_parts = self._build_reply_parts(batch_text, context_info=context_info)\n            if hasattr(self, "_looks_like_no_speech_reply"):\n                reply_parts = [part for part in reply_parts if not self._looks_like_no_speech_reply(part)]\n\n            if not reply_parts:\n                group_skipped += 1\n                continue\n\n            sent_parts: list[str] = []\n            for part in reply_parts[:2]:\n                send_result = self._send_via_gateway(\n                    chat_id=chat_id,\n                    reply=self._sanitize_reply_before_send(part),\n                    message_type="group",\n                )\n                if not send_result.success:\n                    group_skipped += 1\n                    break\n\n                meta = send_result.meta if isinstance(send_result.meta, dict) else {}\n                sent_parts.append(str(meta.get("reply", self._sanitize_reply_before_send(part))).strip())\n\n            sent_parts = [part for part in sent_parts if part]\n            if not sent_parts:\n                continue\n\n            self.last_auto_reply[chat_id] = datetime.now()\n            combined_reply = "\\n\\n".join(sent_parts)\n            self._append_log(chat_id, "group_batch", batch_text, combined_reply)\n            self._remember_recent_exchange(\n                chat_id,\n                "group",\n                "group_batch",\n                batch_text,\n                combined_reply,\n                context_info,\n            )\n\n            sent_reply_records.append(\n                {\n                    "source": "group",\n                    "message_type": "group",\n                    "chat_id": chat_id,\n                    "sender_id": "group_batch",\n                    "sender_name": "主动回复",\n                    "input_text": batch_text,\n                    "reply": combined_reply,\n                    "reply_parts": list(sent_parts),\n                    "kind": "group_pending",\n                }\n            )\n            group_sent += 1\n\n        output = (\n            f"pending轮询完成：私聊发送={sent}, 私聊跳过={skipped}, "\n            f"群聊合并发送={group_sent}, 群聊跳过={group_skipped}, "\n            f"剩余私聊={len(self.pending_private)}, 剩余群聊批次={len(self.pending_group_batches)}"\n        )\n        return ToolResult(\n            True,\n            output,\n            {\n                "sent_replies": sent_reply_records,\n                "reply_count": len(sent_reply_records),\n                "private_sent": sent,\n                "private_skipped": skipped,\n                "group_sent": group_sent,\n                "group_skipped": group_skipped,\n            },\n        )\n'
NEW_WORKSPACE_POLL_PENDING = '\n    def _poll_pending_private(self) -> None:\n        """轮询待发送队列：放到后台线程，避免 DeepSeek/Qwen/NapCat 阻塞 Tkinter 主线程。\n\n        修复点：\n        poll_pending 产生的主动回复不是由 webhook 事件直接返回，\n        所以这里需要读取 result.meta["sent_replies"]，主动写入 Live Ledger。\n        """\n        if not hasattr(self, "qq_panel"):\n            return\n\n        if getattr(self, "_qq_poll_pending_running", False):\n            return\n\n        self._qq_poll_pending_running = True\n\n        def _worker() -> None:\n            try:\n                result = self.qq_panel.tool.run({"command": "poll_pending"})\n\n                def _apply_result() -> None:\n                    try:\n                        meta = result.meta if isinstance(getattr(result, "meta", None), dict) else {}\n\n                        if result.success and (\n                            "发送=" in result.output\n                            or "群聊合并发送=" in result.output\n                            or "pending轮询完成" in result.output\n                        ):\n                            status_var = getattr(self.qq_panel, "qq_status_text", None)\n                            if status_var is not None:\n                                status_var.set(f"轮询待回复: {result.output.strip()[:80]}")\n\n                        sent_replies = meta.get("sent_replies", [])\n                        if isinstance(sent_replies, list):\n                            for item in sent_replies:\n                                if not isinstance(item, dict):\n                                    continue\n\n                                reply = str(item.get("reply", "") or "").strip()\n                                if not reply:\n                                    continue\n\n                                source = str(item.get("source", item.get("message_type", "group")) or "group")\n                                chat_id = str(item.get("chat_id", "") or "")\n                                kind = str(item.get("kind", "") or "pending")\n\n                                send_token_hint = ""\n                                if hasattr(self.qq_panel, "qq_managed_token_var"):\n                                    raw = self.qq_panel.qq_managed_token_var.get().strip()\n                                    if raw:\n                                        send_token_hint = f" [send:{raw[-4:]}]"\n\n                                label = f"🤖 主动回复 {source}/{chat_id}{send_token_hint}"\n                                self._append_chat_message("system", f"{label}\\n{reply}")\n                                self.qq_panel.append_qq_system_message(\n                                    f"主动回复已记录：{kind} | 目标：{source}/{chat_id} | 回复：{reply[:80]}"\n                                )\n\n                    finally:\n                        self._qq_poll_pending_running = False\n\n                self.root.after(0, _apply_result)\n\n            except Exception as exc:\n                def _apply_error() -> None:\n                    try:\n                        if hasattr(self, "qq_panel"):\n                            self.qq_panel.append_qq_system_message(f"轮询待回复异常：{exc}")\n                    finally:\n                        self._qq_poll_pending_running = False\n\n                self.root.after(0, _apply_error)\n\n        threading.Thread(target=_worker, daemon=True).start()\n'


def method_range(src: str, method_name: str, class_name: str | None = None) -> tuple[int, int]:
    tree = ast.parse(src)

    if class_name:
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and node.name == class_name:
                for item in node.body:
                    if isinstance(item, ast.FunctionDef) and item.name == method_name:
                        if item.end_lineno is None:
                            raise RuntimeError("AST 没有 end_lineno")
                        return item.lineno, item.end_lineno
        raise RuntimeError(f"找不到 {class_name}.{method_name}")

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == method_name:
            if node.end_lineno is None:
                raise RuntimeError("AST 没有 end_lineno")
            return node.lineno, node.end_lineno

    raise RuntimeError(f"找不到方法：{method_name}")


def replace_method(src: str, method_name: str, method_text: str, class_name: str | None = None) -> str:
    start, end = method_range(src, method_name, class_name=class_name)
    lines = src.splitlines()
    new_lines = lines[: start - 1] + method_text.strip("\n").splitlines() + lines[end:]
    return "\n".join(new_lines) + "\n"


def patch_tool() -> None:
    if not QQ_TOOL.exists():
        raise SystemExit(f"找不到文件：{QQ_TOOL}")

    src = QQ_TOOL.read_text(encoding="utf-8")
    backup = QQ_TOOL.with_suffix(".py.bak_poll_pending_log_meta")
    backup.write_text(src, encoding="utf-8")

    src2 = replace_method(src, "_poll_pending", NEW_POLL_PENDING, class_name="QQAutoReplyTool")
    compile(src2, str(QQ_TOOL), "exec")
    QQ_TOOL.write_text(src2, encoding="utf-8")
    print(f"✅ 已修复工具层 poll_pending 元数据：{QQ_TOOL}")
    print(f"备份：{backup}")


def patch_workspace() -> None:
    if not WORKSPACE_APP.exists():
        raise SystemExit(f"找不到文件：{WORKSPACE_APP}")

    src = WORKSPACE_APP.read_text(encoding="utf-8")
    backup = WORKSPACE_APP.with_suffix(".py.bak_poll_pending_visible_log")
    backup.write_text(src, encoding="utf-8")

    src2 = replace_method(src, "_poll_pending_private", NEW_WORKSPACE_POLL_PENDING, class_name="WorkspaceFileApp")
    compile(src2, str(WORKSPACE_APP), "exec")
    WORKSPACE_APP.write_text(src2, encoding="utf-8")
    print(f"✅ 已修复前端主动回复日志显示：{WORKSPACE_APP}")
    print(f"备份：{backup}")


def main() -> None:
    patch_tool()
    patch_workspace()
    print()
    print("完成。下一步：")
    print("  python -m py_compile .\\src\\clawmini\\tools\\qq_auto_reply.py")
    print("  python -m py_compile .\\src\\clawmini\\workspace_app.py")
    print("  python app.py")


if __name__ == "__main__":
    main()
