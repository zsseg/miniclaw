#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import ast
from pathlib import Path


PROJECT_ROOT = Path.cwd()
TARGET = PROJECT_ROOT / "src" / "clawmini" / "tools" / "qq_auto_reply.py"

STRICT_PARSE = '\n    def _parse_social_gate_response(self, content: str) -> dict[str, Any] | None:\n        """严格解析 gate 输出。\n\n        旧版太宽松：只要非 JSON 文本里出现 reply/candidate/observe 就会硬猜 action，\n        结果普通表情也可能被误判成 reply，原因显示“宽松解析 gate 输出”。\n        这版只接受：\n        1. 标准 JSON；\n        2. JSON 子串；\n        3. 明确包含 action: reply/candidate/observe 的结构化文本。\n        其他一律返回 None，交给动态兜底/observe。\n        """\n        text = str(content or "").strip()\n        if not text:\n            return None\n\n        # 去掉常见代码块包裹\n        text = re.sub(r"^```(?:json)?\\s*", "", text, flags=re.I).strip()\n        text = re.sub(r"\\s*```$", "", text).strip()\n\n        # 标准 JSON\n        try:\n            data = json.loads(text)\n            return data if isinstance(data, dict) else None\n        except Exception:\n            pass\n\n        # JSON 子串\n        match = re.search(r"\\{[\\s\\S]*\\}", text)\n        if match:\n            candidate = match.group(0)\n            try:\n                data = json.loads(candidate)\n                return data if isinstance(data, dict) else None\n            except Exception:\n                text = candidate\n\n        # 只接受明确 action 字段，不再因为文本里出现 reply 这个单词就误判。\n        m = re.search(r\'["\\\']?action["\\\']?\\s*[:=]\\s*["\\\']?\\s*(reply|candidate|observe)\\b\', text, re.I)\n        if not m:\n            return None\n\n        action = m.group(1).lower()\n\n        confidence = 0.0\n        m_conf = re.search(r\'["\\\']?confidence["\\\']?\\s*[:=]\\s*([01](?:\\.\\d+)?)\', text, re.I)\n        if m_conf:\n            try:\n                confidence = float(m_conf.group(1))\n            except Exception:\n                confidence = 0.0\n\n        reason = ""\n        m_reason = re.search(r\'["\\\']?reason["\\\']?\\s*[:=]\\s*["\\\']([^"\\\']{0,140})\', text, re.I)\n        if m_reason:\n            reason = m_reason.group(1).strip()\n\n        angle = ""\n        m_angle = re.search(r\'["\\\']?angle["\\\']?\\s*[:=]\\s*["\\\']([^"\\\']{0,180})\', text, re.I)\n        if m_angle:\n            angle = m_angle.group(1).strip()\n\n        return {\n            "action": action,\n            "confidence": max(0.0, min(1.0, confidence)),\n            "reason": reason or "解析到结构化 action 字段",\n            "angle": angle,\n        }\n\n    def _is_generic_api_fallback_reply(self, reply: str) -> bool:\n        """识别不该主动发到群里的 API 失败兜底话术。\n\n        主动候选 / poll_pending 里，如果模型请求失败，宁可不说，\n        不要发“接口抽风”这种系统感很强的话。\n        """\n        text = str(reply or "").strip()\n        if not text:\n            return True\n\n        compact = re.sub(r"\\s+", "", text)\n        bad_phrases = [\n            "接口刚才有点抽风",\n            "接口有点抽风",\n            "猫猫先不乱说",\n            "先不乱说",\n            "刚才有点抽风",\n            "请求失败",\n            "API请求失败",\n            "模型请求失败",\n            "AI接口",\n            "接口失败",\n            "网络有点问题",\n            "出了点问题",\n            "服务有点问题",\n            "暂时没想好怎么回",\n            "我这边有点卡",\n        ]\n\n        return any(p in compact for p in bad_phrases)\n'


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


def ensure_strict_helpers(src: str) -> str:
    for name in ("_parse_social_gate_response", "_is_generic_api_fallback_reply"):
        method_text = extract_one_method(STRICT_PARSE, name)
        if method_range(src, name) is not None:
            src = replace_method(src, name, method_text)
        else:
            target = "_social_gate_decide_via_api" if method_range(src, "_social_gate_decide_via_api") else "_build_reply_parts"
            src = insert_before(src, target, method_text)
    return src


def patch_poll_pending_filters(src: str) -> str:
    # 在 poll_pending 的群聊/私聊 pending 中，过滤 API 失败兜底话术。
    # 这个补丁是幂等的。
    if "过滤主动队列里的 API 失败兜底话术" in src:
        return src

    patterns = [
        (
            '            if hasattr(self, "_looks_like_no_speech_reply"):\n'
            '                reply_parts = [part for part in reply_parts if not self._looks_like_no_speech_reply(part)]\n\n'
            '            if not reply_parts:',
            '            if hasattr(self, "_looks_like_no_speech_reply"):\n'
            '                reply_parts = [part for part in reply_parts if not self._looks_like_no_speech_reply(part)]\n'
            '            # 过滤主动队列里的 API 失败兜底话术：主动回复失败就别说，避免显得抽风。\n'
            '            reply_parts = [part for part in reply_parts if not self._is_generic_api_fallback_reply(part)]\n\n'
            '            if not reply_parts:',
        ),
        (
            '            if hasattr(self, "_looks_like_no_speech_reply"):\n'
            '                reply_parts = [part for part in reply_parts if not self._looks_like_no_speech_reply(part)]\n\n'
            '            if not reply_parts:',
            '            if hasattr(self, "_looks_like_no_speech_reply"):\n'
            '                reply_parts = [part for part in reply_parts if not self._looks_like_no_speech_reply(part)]\n'
            '            # 过滤主动队列里的 API 失败兜底话术：主动回复失败就别说，避免显得抽风。\n'
            '            reply_parts = [part for part in reply_parts if not self._is_generic_api_fallback_reply(part)]\n\n'
            '            if not reply_parts:',
        ),
    ]

    replaced = 0
    for old, new in patterns:
        if old in src:
            src = src.replace(old, new)
            replaced += 1

    # 如果你的代码没有 _looks_like_no_speech_reply 过滤块，就在 build_reply_parts 后面补。
    if replaced == 0:
        src = src.replace(
            '            reply_parts = self._build_reply_parts(batch_text, context_info=context_info)\n'
            '            if not reply_parts:',
            '            reply_parts = self._build_reply_parts(batch_text, context_info=context_info)\n'
            '            # 过滤主动队列里的 API 失败兜底话术：主动回复失败就别说，避免显得抽风。\n'
            '            reply_parts = [part for part in reply_parts if not self._is_generic_api_fallback_reply(part)]\n'
            '            if not reply_parts:',
        )
        src = src.replace(
            '            reply_parts = self._build_reply_parts(text, context_info=context_info)\n'
            '            if not reply_parts:',
            '            reply_parts = self._build_reply_parts(text, context_info=context_info)\n'
            '            # 过滤主动队列里的 API 失败兜底话术：主动回复失败就别说，避免显得抽风。\n'
            '            reply_parts = [part for part in reply_parts if not self._is_generic_api_fallback_reply(part)]\n'
            '            if not reply_parts:',
        )

    return src


def patch_candidate_gate_threshold(src: str) -> str:
    # 防止 confidence=0 的解析结果进入候选。
    src = src.replace(
        'if action == "reply" and confidence >= 0.45:',
        'if action == "reply" and confidence >= 0.50:',
    )
    src = src.replace(
        'if action == "candidate" and confidence >= 0.35:',
        'if action == "candidate" and confidence >= 0.42:',
    )
    return src


def main() -> None:
    if not TARGET.exists():
        raise SystemExit(f"找不到文件：{TARGET}")

    src = TARGET.read_text(encoding="utf-8")
    backup = TARGET.with_suffix(".py.bak_strict_gate_no_api_fallback")
    backup.write_text(src, encoding="utf-8")

    src = ensure_strict_helpers(src)
    src = patch_poll_pending_filters(src)
    src = patch_candidate_gate_threshold(src)

    compile(src, str(TARGET), "exec")
    TARGET.write_text(src, encoding="utf-8")

    print("✅ 已修复 gate 宽松误判和主动队列接口抽风话术")
    print("1. gate 不再因为普通文本里出现 reply/candidate 就误判为要回复。")
    print("2. 主动回复/poll_pending 如果只生成“接口抽风”兜底，会直接跳过不发。")
    print("3. 主动候选阈值略微收紧，减少纯表情误入候选。")
    print(f"备份文件：{backup}")
    print("下一步：")
    print("  python -m py_compile .\\src\\clawmini\\tools\\qq_auto_reply.py")
    print("  python app.py")


if __name__ == "__main__":
    main()
