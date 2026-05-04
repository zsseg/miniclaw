#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import ast
import re
from pathlib import Path


PROJECT_ROOT = Path.cwd()
TARGET = PROJECT_ROOT / "src" / "clawmini" / "tools" / "qq_auto_reply.py"

VISION_DEBUG_METHODS = '\n    def _log_system_debug(self, message: str) -> None:\n        """把调试信息尽力打到 UI 和控制台。"""\n        msg = str(message or "").strip()\n        if not msg:\n            return\n\n        try:\n            print(msg)\n        except Exception:\n            pass\n\n        callback_names = (\n            "event_callback",\n            "log_callback",\n            "status_callback",\n            "on_event",\n            "on_log",\n            "ui_log_callback",\n            "message_callback",\n        )\n\n        for attr in callback_names:\n            cb = getattr(self, attr, None)\n            if not callable(cb):\n                continue\n\n            payloads = [\n                ("system", msg),\n                ("系统", msg),\n                ("info", msg),\n                {"level": "info", "type": "system", "title": "系统", "message": msg},\n                msg,\n            ]\n            for payload in payloads:\n                try:\n                    if isinstance(payload, tuple):\n                        cb(*payload)\n                    else:\n                        cb(payload)\n                    return\n                except Exception:\n                    continue\n\n    def _extract_obvious_text_from_image_descriptions(self, descriptions: list[str]) -> str:\n        """从识图结果中提取清晰的图片文字。"""\n        for desc in descriptions or []:\n            s = str(desc or "").strip()\n            if not s:\n                continue\n\n            m = re.search(r"可见文字[:：]\\s*(.*?)(?:\\s+文字清晰度[:：]|\\s+可见内容[:：]|\\s+不确定点[:：]|\\s+可能情绪[:：]|\\s+采信度[:：]|$)", s)\n            if not m:\n                m = re.search(r"(?:文字|图中文字|图片文字)[:：]\\s*(.*?)(?:\\s+文字清晰度[:：]|\\s+可见内容[:：]|\\s+不确定点[:：]|\\s+可能情绪[:：]|\\s+采信度[:：]|$)", s)\n            if not m:\n                continue\n\n            text = m.group(1).strip(" \\n\\r\\t。；;，,")\n            if not text:\n                continue\n\n            if any(x in text for x in ("无", "没有", "看不清", "不清楚", "无法识别")) and len(text) <= 10:\n                continue\n\n            clarity = ""\n            m2 = re.search(r"文字清晰度[:：]\\s*(高|中|低|无)", s)\n            if m2:\n                clarity = m2.group(1)\n            if clarity in {"低", "无"}:\n                continue\n\n            text = re.sub(r"\\s+", "", text)\n            if 1 <= len(text) <= 80:\n                return text\n\n        return ""\n\n    def _summarize_image_vision_for_log(self, descriptions: list[str]) -> str:\n        """把识图结果压成方便看日志的一行。"""\n        descs = [str(x or "").strip() for x in (descriptions or []) if str(x or "").strip()]\n        if not descs:\n            return "无识别结果；可能未配置 DASHSCOPE_API_KEY、图片下载失败、URL 过期，或识图返回为空"\n\n        visible_text = self._extract_obvious_text_from_image_descriptions(descs)\n        first = descs[0]\n\n        clarity = ""\n        m = re.search(r"文字清晰度[:：]\\s*(高|中|低|无)", first)\n        if m:\n            clarity = m.group(1)\n\n        content = ""\n        m2 = re.search(r"可见内容[:：]\\s*(.*?)(?:\\s+不确定点[:：]|\\s+可能情绪[:：]|\\s+采信度[:：]|$)", first)\n        if m2:\n            content = m2.group(1).strip()\n\n        parts = []\n        parts.append(f"文字={visible_text}" if visible_text else "文字=无/不清楚")\n        if clarity:\n            parts.append(f"清晰度={clarity}")\n        if content:\n            parts.append(f"内容={content[:100]}")\n        else:\n            parts.append(f"摘要={first[:140]}")\n\n        return " | ".join(parts)\n\n    def _log_image_vision_debug(\n        self,\n        chat_id: str = "",\n        sender_id: str = "",\n        image_index: int = 1,\n        descriptions: list[str] | None = None,\n        ref: str = "",\n        stage: str = "done",\n    ) -> None:\n        """输出 QQVision 日志，方便判断 OCR 是否开始、是否完成、提取到什么。"""\n        gid = str(chat_id or "?")\n        uid = str(sender_id or "?")\n        if stage == "queued":\n            short_ref = str(ref or "")\n            if len(short_ref) > 80:\n                short_ref = short_ref[:77] + "..."\n            self._log_system_debug(f"[QQVision] 已加入识图队列 group/{gid} user/{uid} image#{image_index}: {short_ref}")\n            return\n\n        if stage == "cached":\n            summary = self._summarize_image_vision_for_log(descriptions or [])\n            self._log_system_debug(f"[QQVision] 命中缓存 group/{gid} user/{uid} image#{image_index}: {summary}")\n            return\n\n        summary = self._summarize_image_vision_for_log(descriptions or [])\n        self._log_system_debug(f"[QQVision] 识图完成 group/{gid} user/{uid} image#{image_index}: {summary}")\n\n    def _start_image_observation_job(\n        self,\n        image_refs: list[str],\n        user_text: str = "",\n        chat_id: str = "",\n        sender_id: str = "",\n    ) -> None:\n        """后台预热识图，并明确输出 queued/done 日志。\n\n        注意：这只是预热和日志，不会主动回复。\n        """\n        self._ensure_image_observation_state()\n\n        refs = [str(ref or "").strip() for ref in (image_refs or []) if str(ref or "").strip()]\n        if not refs:\n            try:\n                self._log_system_debug("[QQVision] 没有可识别的 image url/file，跳过")\n            except Exception:\n                pass\n            return\n\n        try:\n            if not os.getenv("DASHSCOPE_API_KEY", "").strip():\n                self._log_system_debug("[QQVision] 未设置 DASHSCOPE_API_KEY，识图/OCR 不会运行")\n                return\n        except Exception:\n            pass\n\n        for index, ref in enumerate(refs[:3], start=1):\n            key = self._image_observation_key(ref)\n            if not key:\n                continue\n\n            cached = self._image_observation_cache.get(key)\n            if isinstance(cached, dict) and cached.get("descriptions"):\n                try:\n                    self._log_image_vision_debug(chat_id, sender_id, index, cached.get("descriptions", []), ref, stage="cached")\n                except Exception:\n                    pass\n                continue\n\n            if key in self._image_observation_pending:\n                try:\n                    self._log_system_debug(f"[QQVision] 识图已经在队列中 group/{chat_id or \'?\'} user/{sender_id or \'?\'} image#{index}")\n                except Exception:\n                    pass\n                continue\n\n            self._image_observation_pending.add(key)\n            try:\n                self._log_image_vision_debug(chat_id, sender_id, index, [], ref, stage="queued")\n            except Exception:\n                pass\n\n            def _worker(_ref: str = ref, _key: str = key, _index: int = index, _user_text: str = user_text) -> None:\n                descriptions: list[str] = []\n                try:\n                    descriptions = self._describe_images_with_qwen_vl([_ref], _user_text)\n                    self._image_observation_cache[_key] = {\n                        "descriptions": descriptions,\n                        "created_at": datetime.now(),\n                        "ref": _ref,\n                    }\n                except Exception as exc:\n                    descriptions = [f"图片识别失败：{exc}"]\n                    self._image_observation_cache[_key] = {\n                        "descriptions": descriptions,\n                        "created_at": datetime.now(),\n                        "ref": _ref,\n                    }\n                finally:\n                    try:\n                        self._image_observation_pending.discard(_key)\n                    except Exception:\n                        pass\n                    try:\n                        self._log_image_vision_debug(chat_id, sender_id, _index, descriptions, _ref, stage="done")\n                    except Exception:\n                        pass\n\n            try:\n                threading.Thread(target=_worker, daemon=True).start()\n            except Exception as exc:\n                try:\n                    self._image_observation_pending.discard(key)\n                except Exception:\n                    pass\n                try:\n                    self._log_system_debug(f"[QQVision] 启动识图线程失败 group/{chat_id or \'?\'} user/{sender_id or \'?\'} image#{index}: {exc}")\n                except Exception:\n                    pass\n'
VISION_DESCRIBE = '\n    def _describe_images_with_qwen_vl(self, image_refs: list[str], user_text: str = "") -> list[str]:\n        """用 Qwen-VL 单独识图，返回低采信度图片线索，并尽量提取清晰文字。"""\n        api_key = os.getenv("DASHSCOPE_API_KEY", "").strip()\n        if not api_key:\n            return []\n\n        base_url = os.getenv(\n            "QWEN_VL_BASE_URL",\n            "https://dashscope.aliyuncs.com/compatible-mode/v1",\n        ).strip().rstrip("/")\n        model = os.getenv("QWEN_VL_MODEL", "qwen-vl-plus").strip() or "qwen-vl-plus"\n        endpoint = base_url + "/chat/completions"\n        descriptions: list[str] = []\n\n        for index, ref in enumerate(image_refs[:3], start=1):\n            image_part = self._image_ref_to_content_part(ref)\n            if image_part is None:\n                descriptions.append(f"第{index}张图片识别失败：无法转换图片引用")\n                continue\n\n            prompt = (\n                "你在为 QQ 群聊机器人做图片识别。请务必保守，不要过度解读。\\n"\n                "图片可能是表情、梗图、截图、头像、普通照片，也可能只是无语境图片。\\n"\n                "重点：如果图里有清晰可见文字，请准确抄出文字；文字不清楚就写“无”。\\n"\n                "可见文字可以作为较可靠的视觉事实；但图片真正想表达的含义仍然必须低置信处理。\\n"\n                "不要擅自判断图片真正想表达的意思；如果要说含义，必须用“可能/像是/不确定”。\\n"\n                "如果图片没什么明确内容，就直接说信息量低，不要硬解释。\\n"\n                "按格式输出，简短中文：\\n"\n                "可见文字：逐字抄出清晰文字；没有或看不清写“无”。\\n"\n                "文字清晰度：高/中/低/无。\\n"\n                "可见内容：确定能看到的主体、表情、动作。\\n"\n                "不确定点：可能看错、需要上下文、无法确认的内容；没有就写“无明显”。\\n"\n                "可能情绪：低置信度推测，例如“可能是在调侃/疑惑/无语”；不要下定论。\\n"\n                "采信度：高/中/低。只有文字清楚、主体明确时才能高；梗图的含义通常为中或低。\\n"\n                "不要输出客套话，不要说你是模型。"\n            )\n            if user_text:\n                prompt += f"\\n用户配文：{user_text}\\n可以结合配文，但仍不要过度解读图片本意。"\n\n            payload = {\n                "model": model,\n                "temperature": 0.0,\n                "max_tokens": 420,\n                "messages": [\n                    {"role": "user", "content": [{"type": "text", "text": prompt}, image_part]}\n                ],\n            }\n\n            req = urllib.request.Request(\n                endpoint,\n                data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),\n                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},\n                method="POST",\n            )\n\n            try:\n                with urllib.request.urlopen(req, timeout=45) as resp:\n                    body = json.loads(resp.read().decode("utf-8"))\n                content = str(body["choices"][0]["message"]["content"]).strip()\n                if content:\n                    content = re.sub(r"\\s+", " ", content).strip()\n                    descriptions.append(f"第{index}张图片低采信度线索：{content}")\n                else:\n                    descriptions.append(f"第{index}张图片识别失败：模型返回空内容")\n            except Exception as exc:\n                descriptions.append(f"第{index}张图片识别失败：{exc}")\n\n        return descriptions\n'


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


def ensure_methods(src: str) -> str:
    names = [
        "_log_system_debug",
        "_extract_obvious_text_from_image_descriptions",
        "_summarize_image_vision_for_log",
        "_log_image_vision_debug",
        "_start_image_observation_job",
    ]

    for name in names:
        method_text = extract_one_method(VISION_DEBUG_METHODS, name)
        if method_range(src, name) is not None:
            src = replace_method(src, name, method_text)
        else:
            before = "_describe_images_with_qwen_vl" if method_range(src, "_describe_images_with_qwen_vl") else "_handle_message"
            src = insert_before(src, before, method_text)

    if method_range(src, "_describe_images_with_qwen_vl") is not None:
        src = replace_method(src, "_describe_images_with_qwen_vl", VISION_DESCRIBE)

    return src


def patch_start_image_calls(src: str) -> str:
    """把旧的 _start_image_observation_job(image_refs, text) 调用补上 chat_id/sender_id。"""
    src = re.sub(
        r"self\._start_image_observation_job\(\s*image_refs\s*,\s*text\s*\)",
        "self._start_image_observation_job(image_refs, text, chat_id=chat_id, sender_id=sender_id)",
        src,
    )

    src = re.sub(
        r"self\._start_image_observation_job\(\s*image_refs\s*,\s*user_text\s*=\s*text\s*\)",
        "self._start_image_observation_job(image_refs, user_text=text, chat_id=chat_id, sender_id=sender_id)",
        src,
    )

    src = re.sub(
        r"self\._start_image_observation_job\(\s*image_refs\s*\)",
        "self._start_image_observation_job(image_refs, chat_id=chat_id, sender_id=sender_id)",
        src,
    )

    return src


def patch_pure_image_log_line(src: str) -> str:
    if "QQVision 提示：如果没有看到 queued/done" in src:
        return src

    target = 'return ToolResult(True, "纯图片/表情包：已记录为背景并预热识图，不主动回复。")'
    if target not in src:
        return src

    insert = (
        'try:\n'
        '                    self._log_system_debug("[QQVision] 提示：如果没有看到 queued/done 日志，说明启动识图调用没有走到或 DASHSCOPE_API_KEY 未设置")\n'
        '                except Exception:\n'
        '                    pass\n'
        '                ' + target
    )
    return src.replace(target, insert, 1)


def main() -> None:
    if not TARGET.exists():
        raise SystemExit(f"找不到文件：{TARGET}")

    src = TARGET.read_text(encoding="utf-8")
    backup = TARGET.with_suffix(".py.bak_vision_visible_debug")
    backup.write_text(src, encoding="utf-8")

    src = ensure_methods(src)
    src = patch_start_image_calls(src)
    src = patch_pure_image_log_line(src)

    compile(src, str(TARGET), "exec")
    TARGET.write_text(src, encoding="utf-8")

    print("✅ 已增强 QQVision 可见日志")
    print("之后纯图片/表情包预热识图时，应该能看到：")
    print("  [QQVision] 已加入识图队列 ...")
    print("  [QQVision] 识图完成 ... 文字=... | 清晰度=... | 内容=...")
    print("如果没配 DASHSCOPE_API_KEY，会直接显示：")
    print("  [QQVision] 未设置 DASHSCOPE_API_KEY，识图/OCR 不会运行")
    print(f"备份文件：{backup}")
    print("下一步：")
    print("  python -m py_compile .\\src\\clawmini\\tools\\qq_auto_reply.py")
    print("  python app.py")


if __name__ == "__main__":
    main()
