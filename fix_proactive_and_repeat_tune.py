#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import ast
from pathlib import Path

TARGET = Path.cwd() / "src" / "clawmini" / "tools" / "qq_auto_reply.py"

HELPERS = """
    def _proactive_debug_log(self, message: str) -> None:
        raw = str(os.getenv("QQ_PROACTIVE_DEBUG", "1")).strip().lower()
        if raw in {"0", "false", "no", "off", "关", "关闭"}:
            return
        msg = str(message or "").strip()
        if not msg:
            return
        try:
            print(msg)
        except Exception:
            pass
        for attr in ("event_callback", "log_callback", "status_callback", "on_event", "on_log", "ui_log_callback"):
            cb = getattr(self, attr, None)
            if not callable(cb):
                continue
            for payload in (("system", msg), ("系统", msg), ("info", msg), msg):
                try:
                    if isinstance(payload, tuple):
                        cb(*payload)
                    else:
                        cb(payload)
                    return
                except Exception:
                    continue

    def _mark_group_seen_for_proactive(self, chat_id: str) -> None:
        gid = str(chat_id or "").strip()
        if not gid:
            return
        if not hasattr(self, "_proactive_seen_group_ids"):
            self._proactive_seen_group_ids = set()
        try:
            self._proactive_seen_group_ids.add(gid)
        except Exception:
            self._proactive_seen_group_ids = {gid}

    def _proactive_group_id_basic_ok(self, chat_id: str) -> bool:
        gid = str(chat_id or "").strip()
        if not gid or gid in {"0", "None", "null", "undefined"}:
            return False
        if not gid.isdigit() or len(gid) < 6:
            return False
        self_ids = {
            str(getattr(self, "self_user_id", "") or "").strip(),
            str(getattr(self, "qq_self_id", "") or "").strip(),
            str(getattr(self, "bot_qq", "") or "").strip(),
            str(getattr(self, "managed_account", "") or "").strip(),
        }
        return gid not in {x for x in self_ids if x}

    def _collect_proactive_allowed_groups(self) -> list[str]:
        targets = [str(x).strip() for x in (getattr(self, "target_group_ids", []) or []) if str(x).strip()]
        allow_unseen = str(os.getenv("QQ_PROACTIVE_ALLOW_UNSEEN_GROUPS", "0")).strip().lower() in {"1", "true", "yes", "on", "开", "开启"}
        seen = set()
        try:
            seen |= {str(x).strip() for x in getattr(self, "_proactive_seen_group_ids", set()) if str(x).strip()}
        except Exception:
            pass
        try:
            recent = getattr(self, "recent_messages", {}) or {}
            if isinstance(recent, dict):
                for gid, msgs in recent.items():
                    gid_s = str(gid).strip()
                    if gid_s and isinstance(msgs, list) and msgs:
                        seen.add(gid_s)
        except Exception:
            pass

        allowed, skipped = [], []
        for gid in targets:
            if not self._proactive_group_id_basic_ok(gid):
                skipped.append(f"{gid}:非法")
                continue
            if not allow_unseen and gid not in seen:
                skipped.append(f"{gid}:本轮未确认")
                continue
            if gid not in allowed:
                allowed.append(gid)
        if skipped:
            try:
                self._proactive_debug_log("[Proactive] 跳过发起聊天目标：" + "；".join(skipped[:8]))
            except Exception:
                pass
        return allowed

    def _proactive_startup_grace_sec(self) -> float:
        try:
            value = float(os.getenv("QQ_PROACTIVE_STARTUP_GRACE_SEC", "300"))
        except Exception:
            value = 300.0
        return max(0.0, min(value, 3600.0))

    def _proactive_global_cooldown_sec(self) -> float:
        try:
            value = float(os.getenv("QQ_PROACTIVE_GLOBAL_COOLDOWN_SEC", "300"))
        except Exception:
            value = 300.0
        return max(60.0, min(value, 7200.0))

    def _proactive_same_group_cooldown_sec(self) -> float:
        try:
            value = float(os.getenv("QQ_PROACTIVE_SAME_GROUP_COOLDOWN_SEC", "1800"))
        except Exception:
            value = 1800.0
        return max(300.0, min(value, 21600.0))

    def _proactive_text_is_bad_starter(self, text: str) -> bool:
        s = str(text or "").strip()
        if not s:
            return True
        compact = re.sub(r"\\s+", "", s)
        if len(compact) < 6:
            return True
        if any(compact.endswith(x) for x in ("在","打","把","给","跟","和","是","有","没","要","想","能","会","今天群里","你们在","有没有")):
            return True
        bad = (
            "没人理我","都不理我","不理我","怎么没人","没人和我","没人陪我",
            "都去哪了","都去干嘛了","都在偷偷","偷偷想我","偷偷瞒着我",
            "群里好安静","今天群里好安静","今天好安静","这么安静",
            "冒泡","数到三","记小本本","我会闹","拯救一下我",
            "我自己玩去了","我生气了","我要生气","都不找我",
        )
        if any(x in compact for x in bad):
            return True
        if any(x in compact for x in ("刚才","刚刚","你们刚","你刚","刚发","刚说","又在","还在","复读了","我可都看着")):
            return True
        if "主动开话题" in compact or "话题：" in compact:
            return True
        return False
"""

MAYBE_WRAPPER = """
    def _maybe_send_proactive_topic(self) -> dict[str, Any] | None:
        now = datetime.now()
        if not hasattr(self, "_proactive_wrapper_started_at"):
            self._proactive_wrapper_started_at = now
            return None
        try:
            if (now - self._proactive_wrapper_started_at).total_seconds() < self._proactive_startup_grace_sec():
                return None
        except Exception:
            pass

        try:
            batches = getattr(self, "pending_group_batches", {}) or {}
            if isinstance(batches, dict):
                for batch in batches.values():
                    if isinstance(batch, dict) and batch.get("messages"):
                        return None
        except Exception:
            pass

        try:
            last_any = getattr(self, "_last_proactive_any_at", None)
            if isinstance(last_any, datetime) and (now - last_any).total_seconds() < self._proactive_global_cooldown_sec():
                return None
        except Exception:
            pass

        allowed = self._collect_proactive_allowed_groups()
        if not allowed:
            return None

        if not hasattr(self, "_last_proactive_group_at"):
            self._last_proactive_group_at = {}

        filtered = []
        for gid in allowed:
            last_gid = self._last_proactive_group_at.get(str(gid))
            if isinstance(last_gid, datetime) and (now - last_gid).total_seconds() < self._proactive_same_group_cooldown_sec():
                continue
            filtered.append(str(gid))

        if not filtered:
            return None

        old_groups = getattr(self, "target_group_ids", None)
        try:
            self.target_group_ids = filtered
            result = self._maybe_send_proactive_topic_base()
        finally:
            try:
                self.target_group_ids = old_groups
            except Exception:
                pass

        if result:
            try:
                self._last_proactive_any_at = now
                gid = str(result.get("chat_id") or result.get("target") or "")
                if gid:
                    self._last_proactive_group_at[gid] = now
            except Exception:
                pass
        return result
"""

GEN_WRAPPER = """
    def _generate_proactive_topic_text(self, chat_id: str) -> str:
        try:
            text = self._generate_proactive_topic_text_base(chat_id)
        except Exception:
            return ""
        text = str(text or "").strip()
        if not text:
            return ""
        if self._proactive_text_is_bad_starter(text):
            try:
                self._proactive_debug_log(f"[Proactive] 丢弃不自然开场：{text}")
            except Exception:
                pass
            return ""
        return text
"""

EMOTE_METHOD = """
    def _should_join_emote_burst(
        self,
        chat_id: str,
        sender_id: str,
        text: str,
        context_info: dict[str, Any] | None = None,
    ) -> tuple[bool, dict[str, Any] | None, str]:
        context_info = context_info or {}
        if hasattr(self, "_is_pure_visual_repeat_message"):
            is_pure = self._is_pure_visual_repeat_message(text)
        else:
            is_pure = self._is_pure_emote_or_sticker_message(text)
        if not is_pure:
            return False, None, "不是纯表情/图片消息"
        if context_info.get("mentioned") or context_info.get("explicit_self"):
            return False, None, "显式找我，交给正常回复"

        stats = self._recent_emote_burst_stats(chat_id, text)
        try:
            exact_min_count = int(os.getenv("QQ_EMOTE_EXACT_REPEAT_MIN_COUNT", "2"))
        except Exception:
            exact_min_count = 2
        exact_min_count = max(2, min(exact_min_count, 8))

        try:
            exact_min_users = int(os.getenv("QQ_EMOTE_EXACT_REPEAT_MIN_USERS", "1"))
        except Exception:
            exact_min_users = 1
        exact_min_users = max(1, min(exact_min_users, 5))

        try:
            burst_min_count = int(os.getenv("QQ_EMOTE_BURST_MIN_COUNT", "2"))
        except Exception:
            burst_min_count = 2
        burst_min_count = max(2, min(burst_min_count, 10))

        try:
            burst_min_users = int(os.getenv("QQ_EMOTE_BURST_MIN_USERS", "1"))
        except Exception:
            burst_min_users = 1
        burst_min_users = max(1, min(burst_min_users, 5))

        now = datetime.now()
        if not hasattr(self, "_last_emote_burst_join"):
            self._last_emote_burst_join = {}

        try:
            group_cooldown = float(os.getenv("QQ_EMOTE_FAST_GROUP_COOLDOWN_SEC", "5"))
        except Exception:
            group_cooldown = 5.0
        group_cooldown = max(1.5, min(group_cooldown, 120.0))

        last_group = self._last_emote_burst_join.get(f"group:{chat_id}")
        if isinstance(last_group, datetime) and (now - last_group).total_seconds() < group_cooldown:
            return False, None, f"同群冷却中 {group_cooldown:.0f}s"

        exact_count = int(stats.get("exact_count", 0) or 0)
        exact_user_count = int(stats.get("exact_user_count", 0) or 0)
        total_count = int(stats.get("total_count", 0) or 0)
        user_count = int(stats.get("user_count", 0) or 0)

        if stats.get("current_key") and exact_count >= exact_min_count and exact_user_count >= exact_min_users:
            try:
                exact_cooldown = float(os.getenv("QQ_EMOTE_EXACT_REPEAT_COOLDOWN_SEC", "10"))
            except Exception:
                exact_cooldown = 10.0
            exact_cooldown = max(3.0, min(exact_cooldown, 180.0))
            key = str(stats.get("current_key", "") or "")
            last_exact = self._last_emote_burst_join.get(f"exact:{chat_id}:{key}")
            if isinstance(last_exact, datetime) and (now - last_exact).total_seconds() < exact_cooldown:
                return False, None, f"同款冷却中 {exact_cooldown:.0f}s"
            item = self._pick_emote_for_burst_response(chat_id, stats, mode="exact")
            if item:
                self._last_emote_burst_join[f"group:{chat_id}"] = now
                self._last_emote_burst_join[f"exact:{chat_id}:{key}"] = now
                return True, item, "多次复读同一个，跟同款"

        if total_count >= burst_min_count and user_count >= burst_min_users:
            try:
                burst_cooldown = float(os.getenv("QQ_EMOTE_BURST_COOLDOWN_SEC", "15"))
            except Exception:
                burst_cooldown = 15.0
            burst_cooldown = max(5.0, min(burst_cooldown, 240.0))
            last_burst = self._last_emote_burst_join.get(f"burst:{chat_id}")
            if isinstance(last_burst, datetime) and (now - last_burst).total_seconds() < burst_cooldown:
                return False, None, f"复读流冷却中 {burst_cooldown:.0f}s"
            item = self._pick_emote_for_burst_response(chat_id, stats, mode="burst")
            if item:
                self._last_emote_burst_join[f"group:{chat_id}"] = now
                self._last_emote_burst_join[f"burst:{chat_id}"] = now
                return True, item, "大家在刷图/发表情，跟一下"

        return (
            False, None,
            f"未达阈值 exact={exact_count}/{exact_user_count} 需要>={exact_min_count}/{exact_min_users}; "
            f"burst={total_count}/{user_count} 需要>={burst_min_count}/{burst_min_users}",
        )
"""

MARK = """        if source == "group":
            try:
                self._mark_group_seen_for_proactive(chat_id)
            except Exception:
                pass

"""

def method_range(src: str, method_name: str):
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == method_name:
            return node.lineno, node.end_lineno
    return None

def replace_method(src, name, text):
    rng = method_range(src, name)
    if not rng:
        raise RuntimeError(f"找不到方法：{name}")
    start, end = rng
    lines = src.splitlines()
    return "\n".join(lines[:start-1] + text.strip("\n").splitlines() + lines[end:]) + "\n"

def insert_before(src, before, text):
    rng = method_range(src, before)
    if not rng:
        raise RuntimeError(f"找不到插入位置：{before}")
    start, _ = rng
    lines = src.splitlines()
    return "\n".join(lines[:start-1] + text.strip("\n").splitlines() + [""] + lines[start-1:]) + "\n"

def extract(block, name):
    wrapper = "class X:\n" + block
    tree = ast.parse(wrapper)
    lines = wrapper.splitlines()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return "\n".join(lines[node.lineno-1:node.end_lineno])
    raise RuntimeError(f"block 里找不到 {name}")

def wrap_method(src, method_name, base_name, wrapper_text):
    if method_range(src, base_name):
        if method_range(src, method_name):
            return replace_method(src, method_name, wrapper_text)
        return insert_before(src, base_name, wrapper_text)
    rng = method_range(src, method_name)
    if not rng:
        raise RuntimeError(f"找不到方法：{method_name}")
    start, _ = rng
    lines = src.splitlines()
    i = start - 1
    lines[i] = lines[i].replace(f"def {method_name}(", f"def {base_name}(", 1)
    return insert_before("\n".join(lines) + "\n", base_name, wrapper_text)

def patch_mark_seen(src):
    if "_mark_group_seen_for_proactive(chat_id)" in src:
        return src
    marker = "        image_refs = self._extract_image_refs(arguments)\n"
    if marker in src:
        return src.replace(marker, marker + MARK, 1)
    marker = "        text = self._message_to_text(arguments)\n"
    if marker in src:
        return src.replace(marker, marker + MARK, 1)
    print("⚠️ 没找到群活跃插入点，主动开话题仍会依赖 recent_messages。")
    return src

def main():
    if not TARGET.exists():
        raise SystemExit(f"找不到文件：{TARGET}")
    src = TARGET.read_text(encoding="utf-8")
    backup = TARGET.with_suffix(".py.bak_proactive_and_repeat_tune")
    backup.write_text(src, encoding="utf-8")

    for name in [
        "_proactive_debug_log",
        "_mark_group_seen_for_proactive",
        "_proactive_group_id_basic_ok",
        "_collect_proactive_allowed_groups",
        "_proactive_startup_grace_sec",
        "_proactive_global_cooldown_sec",
        "_proactive_same_group_cooldown_sec",
        "_proactive_text_is_bad_starter",
    ]:
        text = extract(HELPERS, name)
        if method_range(src, name):
            src = replace_method(src, name, text)
        else:
            src = insert_before(src, "_maybe_send_proactive_topic" if method_range(src, "_maybe_send_proactive_topic") else "_handle_message", text)

    if method_range(src, "_maybe_send_proactive_topic"):
        src = wrap_method(src, "_maybe_send_proactive_topic", "_maybe_send_proactive_topic_base", MAYBE_WRAPPER)
    else:
        print("⚠️ 没找到 _maybe_send_proactive_topic，跳过发起聊天保护。")

    if method_range(src, "_generate_proactive_topic_text"):
        src = wrap_method(src, "_generate_proactive_topic_text", "_generate_proactive_topic_text_base", GEN_WRAPPER)
    else:
        print("⚠️ 没找到 _generate_proactive_topic_text，跳过发起聊天文本过滤。")

    if method_range(src, "_should_join_emote_burst"):
        src = replace_method(src, "_should_join_emote_burst", EMOTE_METHOD)
    else:
        print("⚠️ 没找到 _should_join_emote_burst，跳过复读阈值调整。")

    src = patch_mark_seen(src)

    compile(src, str(TARGET), "exec")
    TARGET.write_text(src, encoding="utf-8")
    print("✅ 已调整：发起聊天目标/频率 + 复读阈值")
    print("1. 主动开话题只发到本轮确认收到过消息的目标群，避免 group 0 / 私聊 QQ / 已退群。")
    print("2. 默认启动保护 300 秒，全局冷却 300 秒，同群冷却 1800 秒。")
    print("3. 会过滤“没人理我/群好安静/记小本本/数到三”等刷屏式开场。")
    print("4. 复读阈值略降：不同表情/图片流默认 2 条触发；同款仍默认 2 次。")
    print(f"备份文件：{backup}")
    print("下一步：")
    print("  python -m py_compile .\\src\\clawmini\\tools\\qq_auto_reply.py")
    print("  python app.py")
    print()
    print("可调参数：")
    print('  $env:QQ_PROACTIVE_STARTUP_GRACE_SEC="300"')
    print('  $env:QQ_PROACTIVE_GLOBAL_COOLDOWN_SEC="300"')
    print('  $env:QQ_PROACTIVE_SAME_GROUP_COOLDOWN_SEC="1800"')
    print('  $env:QQ_PROACTIVE_ALLOW_UNSEEN_GROUPS="0"')
    print('  $env:QQ_EMOTE_BURST_MIN_COUNT="2"')
    print('  $env:QQ_EMOTE_EXACT_REPEAT_MIN_COUNT="2"')
    print('  $env:QQ_EMOTE_FAST_GROUP_COOLDOWN_SEC="5"')

if __name__ == "__main__":
    main()
