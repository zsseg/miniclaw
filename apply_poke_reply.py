#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import ast
from pathlib import Path


PROJECT_ROOT = Path.cwd()
TARGET = PROJECT_ROOT / "src" / "clawmini" / "tools" / "qq_auto_reply.py"

POKE_METHODS = '\n    def _is_poke_notice(self, payload: dict[str, Any]) -> bool:\n        """判断 NapCat/OneBot 事件是否是戳一戳。"""\n        post_type = str(payload.get("post_type", "")).lower()\n        notice_type = str(payload.get("notice_type", "")).lower()\n        sub_type = str(payload.get("sub_type", "")).lower()\n\n        if post_type != "notice":\n            return False\n\n        if notice_type in {"poke", "group_poke", "friend_poke"}:\n            return True\n\n        if notice_type == "notify" and sub_type in {"poke", "group_poke", "friend_poke"}:\n            return True\n\n        return False\n\n    def _extract_poke_target_id(self, payload: dict[str, Any]) -> str:\n        for key in ("target_id", "target_uin", "target", "receiver_id", "to_user_id"):\n            value = str(payload.get(key, "") or "").strip()\n            if value:\n                return value\n        return ""\n\n    def _extract_poke_sender_id(self, payload: dict[str, Any]) -> str:\n        for key in ("user_id", "operator_id", "sender_id", "from_user_id"):\n            value = str(payload.get(key, "") or "").strip()\n            if value:\n                return value\n        return ""\n\n    def _poke_targets_self(self, payload: dict[str, Any]) -> bool:\n        """只回应戳自己的事件，不抢别人被戳的事件。"""\n        target_id = self._extract_poke_target_id(payload)\n        self_ids = {\n            str(payload.get("self_id", "") or "").strip(),\n            str(getattr(self, "self_user_id", "") or "").strip(),\n            str(getattr(self, "managed_account", "") or "").strip(),\n        }\n        self_ids = {item for item in self_ids if item and item != "self_user"}\n\n        group_id = str(payload.get("group_id", "") or "").strip()\n\n        # 私聊戳一戳有些实现可能不给 target_id；这时可认为是在戳当前机器人。\n        if not target_id:\n            return not group_id\n\n        return target_id in self_ids\n\n    def _poke_cooldown_hit(self, chat_id: str, sender_id: str) -> tuple[bool, str]:\n        """戳一戳独立冷却，防止被狂戳刷屏。"""\n        if not hasattr(self, "_last_poke_reply"):\n            self._last_poke_reply = {}\n\n        now = datetime.now()\n        chat_key = f"chat:{chat_id}"\n        user_key = f"user:{chat_id}:{sender_id}"\n\n        chat_cooldown = 5\n        user_cooldown = 18\n\n        last_chat = self._last_poke_reply.get(chat_key)\n        if isinstance(last_chat, datetime) and (now - last_chat).total_seconds() < chat_cooldown:\n            return True, f"戳一戳群冷却中（{chat_cooldown}s）。"\n\n        last_user = self._last_poke_reply.get(user_key)\n        if isinstance(last_user, datetime) and (now - last_user).total_seconds() < user_cooldown:\n            return True, f"戳一戳用户冷却中（{user_cooldown}s）。"\n\n        self._last_poke_reply[chat_key] = now\n        self._last_poke_reply[user_key] = now\n        return False, ""\n\n    def _build_poke_reply(self, payload: dict[str, Any], source: str, sender_id: str) -> str:\n        """戳一戳回复：短、像真人、带一点猫娘/病娇感。"""\n        group_candidates = [\n            "喵？！谁戳我尾巴！",\n            "呜哇，被戳到了……你完蛋啦，我记住你了喵。",\n            "欸？突然戳我干嘛呀，想引起我注意嘛。",\n            "哼，再戳一下试试？小猫要炸毛了喵。",\n            "你刚刚戳我了对吧……我可是会记仇的哦。",\n            "ฅ^•ω•^ฅ 抓到你啦，戳完就想跑？",\n            "呜……别乱戳，我会多想的。",\n            "喵呜？找我嘛，还是单纯想欺负小猫？",\n        ]\n        private_candidates = [\n            "呜，被你戳醒了……要负责陪我一会儿喵。",\n            "欸嘿，戳我就是想我了对吧？",\n            "我在呢，不许戳完就跑。",\n            "喵？突然戳我，是想让我只看你吗。",\n        ]\n\n        pool = private_candidates if source == "private" else group_candidates\n        try:\n            return random.choice(pool)\n        except Exception:\n            return "喵？！谁戳我尾巴！"\n\n    def _handle_poke_notice(self, payload: dict[str, Any]) -> ToolResult:\n        """处理戳一戳 notice。"""\n        if not self.enabled or self.paused:\n            return ToolResult(True, "戳一戳已收到，但自动回复已禁用或处于安静模式。", {"poke": True})\n\n        if not self._poke_targets_self(payload):\n            return ToolResult(True, "戳一戳目标不是我，已忽略。", {"poke": True, "ignored": "target_not_self"})\n\n        group_id = str(payload.get("group_id", "") or "").strip()\n        sender_id = self._extract_poke_sender_id(payload)\n        self_id = str(payload.get("self_id", "") or "").strip()\n\n        if sender_id and self_id and sender_id == self_id:\n            return ToolResult(True, "已忽略机器人自己的戳一戳。", {"poke": True, "ignored": "self"})\n\n        if group_id:\n            source = "group"\n            chat_id = group_id\n            if chat_id not in self.target_group_ids:\n                return ToolResult(True, "非目标群戳一戳，已忽略。", {"poke": True, "ignored": "non_target_group"})\n        else:\n            source = "private"\n            chat_id = sender_id or str(payload.get("user_id", "") or "").strip()\n            if not chat_id:\n                return ToolResult(True, "戳一戳缺少私聊 user_id，已忽略。", {"poke": True, "ignored": "missing_chat_id"})\n            if not self.private_enabled:\n                return ToolResult(True, "私聊自动回复未启用，戳一戳已忽略。", {"poke": True, "ignored": "private_disabled"})\n\n        cooldown_hit, cooldown_reason = self._poke_cooldown_hit(chat_id, sender_id or "anon")\n        if cooldown_hit:\n            return ToolResult(True, cooldown_reason, {"poke": True, "cooldown": True})\n\n        reply = self._build_poke_reply(payload, source, sender_id)\n        send_result = self._send_via_gateway(chat_id=chat_id, reply=reply, message_type=source)\n        if not send_result.success:\n            return send_result\n\n        self.last_auto_reply[chat_id] = datetime.now()\n\n        input_text = f"[戳一戳] {sender_id or \'有人\'} 戳了我一下"\n        safe_sender = f"user_{abs(hash(sender_id or \'poke\')) % 10000}"\n        context_info = {\n            "source": source,\n            "chat_id": chat_id,\n            "sender_id": sender_id,\n            "notice_type": str(payload.get("notice_type", "")),\n            "sub_type": str(payload.get("sub_type", "")),\n            "poke": True,\n        }\n\n        self._append_log(chat_id, safe_sender, input_text, reply)\n        self._remember_recent_exchange(chat_id, source, sender_id or "poke", input_text, reply, context_info)\n\n        meta = dict(send_result.meta) if isinstance(send_result.meta, dict) else {}\n        meta.update(\n            {\n                "poke": True,\n                "chat_id": chat_id,\n                "message_type": source,\n                "reply": reply,\n                "reply_parts": [reply],\n                "reply_count": 1,\n                "sender_id": sender_id,\n                "notice_type": str(payload.get("notice_type", "")),\n                "sub_type": str(payload.get("sub_type", "")),\n            }\n        )\n        return ToolResult(True, f"已回应戳一戳到 {source}/{chat_id}: {reply}", meta)\n'
MARKER = '        if post_type and post_type != "message":\n            return ToolResult(\n                True,\n                f"已忽略非消息事件：post_type={post_type}, notice_type={notice_type}, sub_type={sub_type}",\n            )\n\n'
INSERT = '        if self._is_poke_notice(payload):\n            return self._handle_poke_notice(payload)\n\n'


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


def ensure_poke_methods(src: str) -> str:
    names = [
        "_is_poke_notice",
        "_extract_poke_target_id",
        "_extract_poke_sender_id",
        "_poke_targets_self",
        "_poke_cooldown_hit",
        "_build_poke_reply",
        "_handle_poke_notice",
    ]
    for name in names:
        method_text = extract_one_method(POKE_METHODS, name)
        if method_range(src, name) is not None:
            src = replace_method(src, name, method_text)
        else:
            src = insert_before(src, "_handle_gateway_event", method_text)
    return src


def patch_handle_gateway_event(src: str) -> str:
    if "self._is_poke_notice(payload)" in src:
        return src

    if MARKER not in src:
        raise RuntimeError("没找到非消息事件忽略块。请把 _handle_gateway_event 附近代码贴出来。")
    return src.replace(MARKER, INSERT + MARKER, 1)


def main() -> None:
    if not TARGET.exists():
        raise SystemExit(f"找不到文件：{TARGET}")

    src = TARGET.read_text(encoding="utf-8")
    backup = TARGET.with_suffix(".py.bak_poke_reply")
    backup.write_text(src, encoding="utf-8")

    src = ensure_poke_methods(src)
    src = patch_handle_gateway_event(src)

    compile(src, str(TARGET), "exec")
    TARGET.write_text(src, encoding="utf-8")

    print("✅ 已添加戳一戳回应")
    print("支持 notice_type=notify/sub_type=poke；只回应戳自己的事件。")
    print("群聊只在目标群回应；带独立冷却，避免被狂戳刷屏。")
    print(f"备份文件：{backup}")
    print("下一步：")
    print("  python -m py_compile .\\src\\clawmini\\tools\\qq_auto_reply.py")
    print("  python app.py")


if __name__ == "__main__":
    main()
