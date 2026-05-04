#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import ast
from pathlib import Path


PROJECT_ROOT = Path.cwd()
TARGET = PROJECT_ROOT / "src" / "clawmini" / "tools" / "qq_auto_reply.py"

NEW_PICKER = '\n    def _pick_collected_emote_for_reply(self, chat_id: str) -> dict[str, Any] | None:\n        """从当前群收集到的表情里挑一个。\n\n        不避开最近发过的表情，只做“使用次数均衡 + 随机扰动”来保证整体多样化：\n        - 优先从 use_count 最低的一批里挑；\n        - 表情池越大，可选池越大；\n        - 不用 recent_keys，不会因为“刚发过”而硬排除。\n        """\n        self._ensure_emote_pool_loaded()\n        gid = str(chat_id)\n        pool = self._group_emote_pool.get(gid, [])\n        if not isinstance(pool, list) or not pool:\n            return None\n\n        now = datetime.now()\n        valid: list[dict[str, Any]] = []\n\n        try:\n            ttl_hours = float(os.getenv("QQ_EMOTE_POOL_TTL_HOURS", "24"))\n        except Exception:\n            ttl_hours = 24.0\n        ttl_hours = max(1.0, min(ttl_hours, 168.0))\n\n        for item in pool:\n            if not isinstance(item, dict):\n                continue\n\n            emote_type = str(item.get("type", "") or "")\n            if emote_type not in {"face", "image"}:\n                continue\n\n            key = str(item.get("key", "") or "")\n            if not key:\n                continue\n\n            # 图片 URL/rkey 可能过期；face 可以长期用。\n            if emote_type == "image":\n                seen_at = item.get("last_seen_at") or item.get("first_seen_at")\n                if seen_at:\n                    try:\n                        dt = datetime.fromisoformat(str(seen_at))\n                        if (now - dt).total_seconds() > ttl_hours * 3600:\n                            continue\n                    except Exception:\n                        pass\n\n            valid.append(item)\n\n        if not valid:\n            return None\n\n        # 使用次数越少越优先。这样不是“避开最近”，而是让整个池子长期更均衡。\n        def _use_count(item: dict[str, Any]) -> int:\n            try:\n                return int(item.get("use_count", 0) or 0)\n            except Exception:\n                return 0\n\n        min_use = min(_use_count(item) for item in valid)\n\n        # 可选池：优先选使用次数最低或接近最低的一批。\n        # 池子越大，候选范围稍微放宽，避免太机械。\n        if len(valid) <= 5:\n            allowed_delta = 0\n        elif len(valid) <= 20:\n            allowed_delta = 1\n        else:\n            allowed_delta = 2\n\n        candidates = [item for item in valid if _use_count(item) <= min_use + allowed_delta]\n        if not candidates:\n            candidates = valid\n\n        weights: list[float] = []\n        for item in candidates:\n            use_count = _use_count(item)\n\n            # 低使用次数权重大；不是按最近排除。\n            weight = 1.0 / (1.0 + use_count)\n\n            # 图片表情略微加权，避免全是内置黄脸；但不强行。\n            if str(item.get("type", "")) == "image":\n                weight *= 1.10\n            else:\n                weight *= 0.95\n\n            # 加随机扰动，避免同 use_count 时永远选固定顺序。\n            try:\n                weight *= random.uniform(0.65, 1.45)\n            except Exception:\n                pass\n\n            weights.append(max(0.01, weight))\n\n        try:\n            picked = random.choices(candidates, weights=weights, k=1)[0]\n        except Exception:\n            try:\n                picked = random.choice(candidates)\n            except Exception:\n                picked = candidates[-1]\n\n        return picked\n'


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


def main() -> None:
    if not TARGET.exists():
        raise SystemExit(f"找不到文件：{TARGET}")

    src = TARGET.read_text(encoding="utf-8")
    backup = TARGET.with_suffix(".py.bak_emote_diversity_no_recent_avoid")
    backup.write_text(src, encoding="utf-8")

    if method_range(src, "_pick_collected_emote_for_reply") is None:
        raise RuntimeError(
            "找不到 _pick_collected_emote_for_reply。"
            "说明你可能还没应用“表情池/回复时发表情”的补丁，先应用那个再跑这个。"
        )

    src = replace_method(src, "_pick_collected_emote_for_reply", NEW_PICKER)

    # 清理上一版可能留下的 recent key 逻辑变量名，避免误会；不强删其它方法。
    # 选择逻辑已经完全不使用 _recent_sent_emote_keys / QQ_EMOTE_AVOID_RECENT_N。
    compile(src, str(TARGET), "exec")
    TARGET.write_text(src, encoding="utf-8")

    print("✅ 已改成：不避开最近表情，只做整体多样化")
    print("现在选择表情时不会因为最近发过而硬排除。")
    print("多样化方式：优先从 use_count 最低的一批表情里随机挑，长期保证表情池更均衡。")
    print("已不再使用 QQ_EMOTE_AVOID_RECENT_N。")
    print(f"备份文件：{backup}")
    print("下一步：")
    print("  python -m py_compile .\\src\\clawmini\\tools\\qq_auto_reply.py")
    print("  python app.py")


if __name__ == "__main__":
    main()
