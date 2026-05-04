#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
import ast
from pathlib import Path

PROJECT_ROOT = Path.cwd()
TARGET = PROJECT_ROOT / "src" / "clawmini" / "tools" / "qq_auto_reply.py"

NEW_DESCRIBE_IMAGES = '\n    def _describe_images_with_qwen_vl(self, image_refs: list[str], user_text: str = "") -> list[str]:\n        """用 Qwen-VL 单独识图，返回低采信度图片线索。\n\n        只描述可见信息，不把表情包/梗图的“含义”当成事实。\n        """\n        api_key = os.getenv("DASHSCOPE_API_KEY", "").strip()\n        if not api_key:\n            return []\n\n        base_url = os.getenv(\n            "QWEN_VL_BASE_URL",\n            "https://dashscope.aliyuncs.com/compatible-mode/v1",\n        ).strip().rstrip("/")\n        model = os.getenv("QWEN_VL_MODEL", "qwen-vl-plus").strip() or "qwen-vl-plus"\n        endpoint = base_url + "/chat/completions"\n        descriptions: list[str] = []\n\n        for index, ref in enumerate(image_refs[:3], start=1):\n            image_part = self._image_ref_to_content_part(ref)\n            if image_part is None:\n                continue\n\n            prompt = (\n                "你在为 QQ 群聊机器人做图片识别。请务必保守，不要过度解读。\\n"\n                "图片可能是表情包、梗图、截图、头像、普通照片，也可能只是无语境图片。\\n"\n                "只描述明确看见的视觉信息，不要把猜测当事实。\\n"\n                "不要擅自判断图片真正想表达的意思；如果要说含义，必须用“可能/像是/不确定”。\\n"\n                "如果图片没什么明确内容，就直接说信息量低，不要硬解释。\\n"\n                "按格式输出，简短中文：\\n"\n                "可见内容：确定能看到的主体、文字、表情、动作。\\n"\n                "不确定点：可能看错、需要上下文、无法确认的内容；没有就写“无明显”。\\n"\n                "可能情绪：低置信度推测，例如“可能是在调侃/疑惑/无语”；不要下定论。\\n"\n                "采信度：高/中/低。只有文字清楚、主体明确时才能高；表情包、梗图、纯表情通常为中或低。\\n"\n                "不要输出客套话，不要说你是模型。"\n            )\n            if user_text:\n                prompt += f"\\n用户配文：{user_text}\\n可以结合配文，但仍不要过度解读图片本意。"\n\n            payload = {\n                "model": model,\n                "temperature": 0.0,\n                "max_tokens": 360,\n                "messages": [\n                    {"role": "user", "content": [{"type": "text", "text": prompt}, image_part]}\n                ],\n            }\n            req = urllib.request.Request(\n                endpoint,\n                data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),\n                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},\n                method="POST",\n            )\n            try:\n                with urllib.request.urlopen(req, timeout=45) as resp:\n                    body = json.loads(resp.read().decode("utf-8"))\n                content = str(body["choices"][0]["message"]["content"]).strip()\n                if content:\n                    content = re.sub(r"\\s+", " ", content).strip()\n                    descriptions.append(f"第{index}张图片低采信度线索：{content}")\n            except Exception as exc:\n                descriptions.append(f"第{index}张图片识别失败：{exc}")\n\n        return descriptions\n'
HELPERS = '\n    def _ensure_image_observation_state(self) -> None:\n        if not hasattr(self, "_image_observation_cache"):\n            self._image_observation_cache = {}\n        if not hasattr(self, "_image_observation_pending"):\n            self._image_observation_pending = set()\n\n    def _image_observation_key(self, ref: str) -> str:\n        raw = str(ref or "").strip()\n        if not raw:\n            return ""\n        try:\n            import hashlib\n            return hashlib.sha1(raw.encode("utf-8", errors="ignore")).hexdigest()\n        except Exception:\n            return raw[:200]\n\n    def _text_asks_about_recent_image(self, text: str) -> bool:\n        clean = str(text or "").strip()\n        if not clean:\n            return False\n        image_words = [\n            "这图", "这个图", "这张图", "刚才的图", "上面的图", "上一张图",\n            "那图", "那个图", "那张图", "图片", "图里", "图上",\n            "表情包", "表情", "梗图",\n        ]\n        ask_words = [\n            "什么意思", "啥意思", "什么梗", "看懂", "看一下", "看看",\n            "解释", "表达", "意思", "怎么回事", "这是啥", "这是哪",\n            "像什么", "在干嘛", "啥图",\n        ]\n        return any(w in clean for w in image_words) and any(w in clean for w in ask_words)\n\n    def _start_image_observation_job(\n        self,\n        image_refs: list[str],\n        user_text: str = "",\n        chat_id: str = "",\n        sender_id: str = "",\n    ) -> None:\n        """后台预热识图，不直接触发回复。"""\n        self._ensure_image_observation_state()\n\n        refs = [str(ref or "").strip() for ref in (image_refs or []) if str(ref or "").strip()]\n        if not refs:\n            return\n\n        for ref in refs[:3]:\n            key = self._image_observation_key(ref)\n            if not key:\n                continue\n            if key in self._image_observation_cache or key in self._image_observation_pending:\n                continue\n\n            self._image_observation_pending.add(key)\n\n            def _worker(_ref: str = ref, _key: str = key, _user_text: str = user_text) -> None:\n                try:\n                    desc = self._describe_images_with_qwen_vl([_ref], _user_text)\n                    self._image_observation_cache[_key] = {\n                        "descriptions": desc,\n                        "created_at": datetime.now(),\n                        "ref": _ref,\n                    }\n                except Exception as exc:\n                    self._image_observation_cache[_key] = {\n                        "descriptions": [f"图片识别失败：{exc}"],\n                        "created_at": datetime.now(),\n                        "ref": _ref,\n                    }\n                finally:\n                    try:\n                        self._image_observation_pending.discard(_key)\n                    except Exception:\n                        pass\n\n            try:\n                threading.Thread(target=_worker, daemon=True).start()\n            except Exception:\n                # 如果线程起不来，后续显式问图时还会同步等待/降级。\n                self._image_observation_pending.discard(key)\n\n    def _get_image_observations(\n        self,\n        image_refs: list[str],\n        user_text: str = "",\n        context_info: dict[str, Any] | None = None,\n    ) -> list[str]:\n        """获取图片视觉线索。\n\n        非显式问图：只拿已缓存结果，不等待。\n        显式问“这图什么意思”：等待一小会儿，避免用户问了但识图还没出来。\n        """\n        context_info = context_info or {}\n        self._ensure_image_observation_state()\n\n        refs = [str(ref or "").strip() for ref in (image_refs or []) if str(ref or "").strip()]\n        if not refs:\n            return []\n\n        explicit_question = bool(context_info.get("explicit_image_question")) or self._text_asks_about_recent_image(user_text)\n        self._start_image_observation_job(refs, user_text=user_text, chat_id=str(context_info.get("chat_id", "")), sender_id=str(context_info.get("sender_id", "")))\n\n        wait_sec = 0.0\n        if explicit_question:\n            try:\n                wait_sec = float(os.getenv("QQ_IMAGE_QUESTION_WAIT_SEC", "8"))\n            except Exception:\n                wait_sec = 8.0\n            wait_sec = max(2.0, min(wait_sec, 12.0))\n\n        if wait_sec > 0:\n            try:\n                import time as _time\n                deadline = _time.time() + wait_sec\n                while _time.time() < deadline:\n                    missing = []\n                    for ref in refs[:3]:\n                        key = self._image_observation_key(ref)\n                        if key and key not in self._image_observation_cache:\n                            missing.append(key)\n                    if not missing:\n                        break\n                    _time.sleep(0.25)\n            except Exception:\n                pass\n\n        descriptions: list[str] = []\n        for ref in refs[:3]:\n            key = self._image_observation_key(ref)\n            item = self._image_observation_cache.get(key, {}) if key else {}\n            if isinstance(item, dict):\n                for desc in item.get("descriptions", []) or []:\n                    desc = str(desc or "").strip()\n                    if desc and "识别失败" not in desc:\n                        descriptions.append(desc)\n\n        if not descriptions and explicit_question:\n            descriptions.append("图片视觉线索暂时还没完全出来；只能低置信度回答，不要假装已经准确看懂。")\n\n        return descriptions\n\n    def _wrap_image_observation_block(self, descriptions: list[str]) -> str:\n        clean_items: list[str] = []\n        for item in descriptions:\n            desc = str(item or "").strip()\n            if not desc or "识别失败" in desc:\n                continue\n            clean_items.append(desc)\n\n        if not clean_items:\n            return "图片视觉线索：暂时无法识别清楚；不要臆测图片含义。"\n\n        image_block = "\\n".join(f"- {item}" for item in clean_items)\n        return (\n            "图片视觉线索（低采信度，仅供参考，可能误读）：\\n"\n            f"{image_block}\\n"\n            "使用规则：不要把以上内容当成图片真实含义；优先结合群友对图片的评论和配文。"\n            "如果没人问图，就只当背景；如果有人问图，回复时用“可能/像是/不太确定”。"\n            "不要强行解释梗图，不要编造图外信息。"\n        )\n'

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
        "_ensure_image_observation_state",
        "_image_observation_key",
        "_text_asks_about_recent_image",
        "_start_image_observation_job",
        "_get_image_observations",
        "_wrap_image_observation_block",
    ]
    for name in names:
        method_text = extract_one_method(HELPERS, name)
        if method_range(src, name) is not None:
            src = replace_method(src, name, method_text)
        else:
            target = "_build_user_content" if method_range(src, "_build_user_content") else "_handle_message"
            src = insert_before(src, target, method_text)
    return src

def patch_handle_message(src: str) -> str:
    # 图片到达时先后台预热识图，但不因为图片本身触发回复。
    old = '        image_refs = self._extract_image_refs(arguments)\n\n        context_info = {'
    new = '        image_refs = self._extract_image_refs(arguments)\n        if image_refs:\n            try:\n                self._start_image_observation_job(image_refs, user_text=text, chat_id=chat_id, sender_id=sender_id)\n            except Exception:\n                pass\n\n        context_info = {'
    if old in src:
        src = src.replace(old, new, 1)
    else:
        print("⚠️ 没找到 image_refs 初始化插入点，已跳过后台预热。")

    marker = '            should_reply, reply_reason = self._should_reply_to_group_message(\n'
    insert = '''            if not image_refs and self._text_asks_about_recent_image(text):
                recent_image_refs = []
                try:
                    if hasattr(self, "_collect_recent_group_image_refs"):
                        recent_image_refs = self._collect_recent_group_image_refs(chat_id, sender_id)
                except Exception:
                    recent_image_refs = []
                if recent_image_refs:
                    image_refs = list(recent_image_refs)
                    context_info["image_refs"] = list(recent_image_refs)
                    context_info["recent_image_context"] = True
                    context_info["explicit_image_question"] = True
                    try:
                        self._start_image_observation_job(image_refs, user_text=text, chat_id=chat_id, sender_id=sender_id)
                    except Exception:
                        pass

            if image_refs and self._text_asks_about_recent_image(text):
                context_info["explicit_image_question"] = True

'''
    if marker in src and "explicit_image_question" not in src[src.find(marker)-900:src.find(marker)]:
        src = src.replace(marker, insert + marker, 1)
    return src

def patch_build_user_content(src: str) -> str:
    src = src.replace(
        'descriptions = self._describe_images_with_qwen_vl(image_refs, base_text)',
        'descriptions = self._get_image_observations(image_refs, base_text, context_info=context_info)'
    )

    old = '''                if clean_descriptions:
                    image_block = "\\n".join(f"- {item}" for item in clean_descriptions)
                    if base_text:
                        return f"{base_text}\\n\\n图片内容：\\n{image_block}"
                    return f"用户发送了图片。\\n\\n图片内容：\\n{image_block}"'''
    new = '''                if clean_descriptions:
                    image_block = self._wrap_image_observation_block(clean_descriptions)
                    context_info["image_observation_block"] = image_block
                    context_info["image_observation_confidence"] = "low"
                    if base_text:
                        return f"{base_text}\\n\\n{image_block}"
                    return f"用户发送了图片。\\n\\n{image_block}"'''
    if old in src:
        src = src.replace(old, new, 1)
    else:
        src = src.replace('图片内容：\\n{image_block}', '{image_block}')
    src = src.replace(
        'return f"{base_text}\\n\\n图片内容：暂时无法识别清楚。"',
        'return f"{base_text}\\n\\n图片视觉线索：暂时无法识别清楚；不要臆测图片含义。"'
    )
    src = src.replace(
        'return "用户发送了一张图片，但图片内容暂时无法识别清楚。"',
        'return "用户发送了一张图片，但图片视觉线索暂时无法识别清楚；不要臆测图片含义。"'
    )
    return src

def patch_prompt(src: str) -> str:
    addition = (
        " 图片识别结果只当低采信度视觉线索，不要把识图模型的解释当成事实。"
        "图片经常只是表情包、魔怔图、梗图或情绪背景，不一定代表发送者真实意思。"
        "没人问图片时，不要主动解释图片；有人问图片什么意思时，可以回答，但要说“可能/像是/不太确定”。"
        "解释时优先结合群友对图片的评论和配文，不要强行解释没内容的图片。"
    )
    if addition in src:
        return src
    for marker in (
        "不要输出 Markdown、标题、编号、解释性前言。",
        "回复要短，像 QQ 聊天，不要写文章。",
        "群聊里要结合上下文，合并共同话题，不要逐条复读。",
    ):
        if marker in src:
            return src.replace(marker, marker + addition, 1)
    return src

def patch_sanitize_keywords(src: str) -> str:
    extras = [
        "图片视觉线索（低采信度",
        "低采信度，仅供参考",
        "使用规则：不要把以上内容当成图片真实含义",
        "不要强行解释梗图",
        "不要编造图外信息",
        "图片视觉线索暂时还没完全出来",
    ]
    anchor = '"来自 Qwen-VL",'
    for key in extras:
        if key not in src and anchor in src:
            src = src.replace(anchor, anchor + f'\n            "{key}",', 1)
    return src

def main() -> None:
    if not TARGET.exists():
        raise SystemExit(f"找不到文件：{TARGET}")

    src = TARGET.read_text(encoding="utf-8")
    backup = TARGET.with_suffix(".py.bak_image_timing_confidence")
    backup.write_text(src, encoding="utf-8")

    src = replace_method(src, "_describe_images_with_qwen_vl", NEW_DESCRIBE_IMAGES)
    src = ensure_helpers(src)
    src = patch_handle_message(src)
    src = patch_build_user_content(src)
    src = patch_prompt(src)
    src = patch_sanitize_keywords(src)

    compile(src, str(TARGET), "exec")
    TARGET.write_text(src, encoding="utf-8")

    print("✅ 已修复图片识别时机和采信度")
    print("纯图片只后台预热识图，不主动回复；有人问图时会等待识图结果一小会儿。")
    print("识图结果会作为低采信度视觉线索，结合群友评论，不再强行解释图片本意。")
    print(f"备份文件：{backup}")
    print("下一步：")
    print("  python -m py_compile .\\src\\clawmini\\tools\\qq_auto_reply.py")
    print("  python app.py")

if __name__ == "__main__":
    main()
