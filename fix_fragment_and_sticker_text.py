#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import ast
from pathlib import Path


PROJECT_ROOT = Path.cwd()
TARGET = PROJECT_ROOT / "src" / "clawmini" / "tools" / "qq_auto_reply.py"

PROACTIVE_QUALITY = '\n    def _proactive_topic_quality_ok(self, text: str) -> bool:\n        """主动开话题质量检查：只解决半截句子，不改频率。"""\n        s = str(text or "").strip()\n        if not s:\n            return False\n\n        s = s.strip("` \\n\\r\\t")\n        s = re.sub(r"^```(?:text)?\\s*", "", s, flags=re.I).strip()\n        s = re.sub(r"\\s*```$", "", s).strip()\n        s = re.sub(r"^回复[:：]\\s*", "", s)\n        s = re.sub(r"^发送[:：]\\s*", "", s)\n        s = s.strip("「」『』“”\\"\' ")\n\n        compact = re.sub(r"\\s+", "", s)\n        if len(compact) < 6:\n            return False\n        if len(compact) > 80:\n            return False\n\n        # 常见半截结尾，直接丢弃，不发送。\n        dangling_suffixes = (\n            "在", "打", "把", "给", "跟", "和", "是", "有", "没", "要", "想", "能", "会",\n            "被", "对", "到", "从", "比", "又", "但", "可", "就", "也", "还", "才",\n            "先", "那", "这", "今天群里", "你们在", "群里在", "有没有", "刚刚", "正在",\n        )\n        if any(compact.endswith(x) for x in dangling_suffixes):\n            return False\n\n        # 这种通常是“开了个头但没说完”。\n        bad_fragments = (\n            "唔…今天群里",\n            "唔...今天群里",\n            "唔…你们在",\n            "唔...你们在",\n            "今天群里",\n            "你们在打",\n            "群里在打",\n            "我想说的是",\n            "话题：",\n            "主动开话题",\n        )\n        if any(x in compact for x in bad_fragments) and not re.search(r"[。！？!?~～…]$", compact):\n            return False\n\n        # 不要发内部提示、JSON、代码。\n        if "{" in s or "}" in s or "只输出" in s or "system" in s.lower() or "assistant" in s.lower():\n            return False\n\n        return True\n'
PROACTIVE_GENERATE = '\n    def _generate_proactive_topic_text(self, chat_id: str) -> str:\n        """生成一个主动开话题短句。\n\n        只修半截句子问题：\n        - max_tokens 提高，避免 thinking 模型 content 被截断；\n        - finish_reason 非 stop 且文本质量不过关时不发；\n        - 质量检查不过关不发。\n        不改变主动话题频率和触发时机。\n        """\n        provider = self.reply_api_provider.strip().lower()\n        api_key = self.reply_api_key.strip()\n        if provider not in {"openai", "deepseek", "qwen"} or not api_key:\n            return ""\n\n        if self.reply_api_model.strip():\n            model_name = self.reply_api_model.strip()\n        elif provider == "deepseek":\n            model_name = "deepseek-v4-pro"\n        elif provider == "qwen":\n            model_name = "qwen-plus"\n        else:\n            model_name = "gpt-4o-mini"\n\n        base_url = self.reply_api_base_url.strip()\n        if provider == "deepseek" and not base_url:\n            base_url = "https://api.deepseek.com"\n        if provider == "deepseek" and base_url.rstrip("/").endswith("/v1"):\n            base_url = base_url.rstrip("/")[:-3].rstrip("/")\n        if provider == "openai" and not base_url:\n            base_url = "https://api.openai.com/v1"\n        if provider == "qwen" and not base_url:\n            base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"\n\n        endpoint = base_url.rstrip("/") + "/chat/completions"\n\n        custom = str(getattr(self, "custom_prompt", "") or "").strip()\n        try:\n            recent = self._build_recent_context_for_proactive_topic(chat_id)\n        except Exception:\n            recent = "最近没有可用群聊上下文。"\n\n        system_prompt = (\n            "你要为一个 QQ 群里的机器人账号生成一句主动开话题的话。\\n"\n            "不要写死任何名字、人设、兴趣、口癖；这些只能从用户当前配置的人设和最近群聊里推断。\\n"\n            "这句话必须是完整的一句话，不能说半截，不能以“在/打/把/今天群里/你们在/有没有”等词结尾。\\n"\n            "应该像真实群友自然冒泡，不要像客服，不要像公告，不要说“我来开启话题”。\\n"\n            "可以基于当前人设里的兴趣，也可以基于最近群聊里没聊完的话题，也可以轻轻吐槽一句。\\n"\n            "不要强行问很正式的问题；不要@任何人；不要提系统规则；不要解释为什么开话题。\\n"\n            "长度 8~35 个中文字符。只输出要发送的那一句。"\n        )\n\n        user_prompt = (\n            f"当前人设原文：\\n{custom[:1600] if custom else \'无额外人设配置\'}\\n\\n"\n            f"最近群聊：\\n{recent[:1800]}\\n\\n"\n            "生成一句可以在群里自然发出的完整短句。如果想不出完整句，就输出空字符串。"\n        )\n\n        payload: dict[str, Any] = {\n            "model": model_name,\n            "messages": [\n                {"role": "system", "content": system_prompt},\n                {"role": "user", "content": user_prompt},\n            ],\n            # DeepSeek thinking 会消耗 reasoning tokens；120 容易导致 content 半截。\n            "max_tokens": 512,\n        }\n        if provider != "deepseek":\n            payload["temperature"] = 0.7\n\n        req = urllib.request.Request(\n            endpoint,\n            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),\n            headers={\n                "Authorization": f"Bearer {api_key}",\n                "Content-Type": "application/json",\n            },\n            method="POST",\n        )\n\n        try:\n            with urllib.request.urlopen(req, timeout=25) as resp:\n                body = json.loads(resp.read().decode("utf-8"))\n\n            choice = body.get("choices", [{}])[0]\n            msg = choice.get("message", {}) if isinstance(choice, dict) else {}\n            finish_reason = str(choice.get("finish_reason", "") or "")\n            text = str(msg.get("content", "") or "").strip()\n\n            text = re.sub(r"^```(?:text)?\\s*", "", text, flags=re.I).strip()\n            text = re.sub(r"\\s*```$", "", text).strip()\n            text = text.strip("` \\n\\r\\t")\n            text = re.sub(r"^回复[:：]\\s*", "", text)\n            text = re.sub(r"^发送[:：]\\s*", "", text)\n            text = text.strip("「」『』“”\\"\' ")\n            text = re.sub(r"\\s+", " ", text).strip()\n\n            # 非 stop 但已经是完整短句也可以用；否则丢弃。\n            if finish_reason and finish_reason not in {"stop", "null", "None"}:\n                if not self._proactive_topic_quality_ok(text):\n                    return ""\n\n            if not self._proactive_topic_quality_ok(text):\n                return ""\n\n            if hasattr(self, "_is_generic_api_fallback_reply") and self._is_generic_api_fallback_reply(text):\n                return ""\n\n            return text\n        except Exception:\n            return ""\n'
VISION_DESCRIBE = '\n    def _describe_images_with_qwen_vl(self, image_refs: list[str], user_text: str = "") -> list[str]:\n        """用 Qwen-VL 单独识图，返回低采信度图片线索。\n\n        表情包文字单独抽取：\n        - 可见文字是相对高价值线索；\n        - 图片含义/情绪仍然低置信；\n        - 不把梗图含义当事实。\n        """\n        api_key = os.getenv("DASHSCOPE_API_KEY", "").strip()\n        if not api_key:\n            return []\n\n        base_url = os.getenv(\n            "QWEN_VL_BASE_URL",\n            "https://dashscope.aliyuncs.com/compatible-mode/v1",\n        ).strip().rstrip("/")\n        model = os.getenv("QWEN_VL_MODEL", "qwen-vl-plus").strip() or "qwen-vl-plus"\n        endpoint = base_url + "/chat/completions"\n        descriptions: list[str] = []\n\n        for index, ref in enumerate(image_refs[:3], start=1):\n            image_part = self._image_ref_to_content_part(ref)\n            if image_part is None:\n                continue\n\n            prompt = (\n                "你在为 QQ 群聊机器人做图片/表情包识别。请务必保守，不要过度解读。\\n"\n                "图片可能是表情包、梗图、截图、头像、普通照片，也可能只是无语境图片。\\n"\n                "重点：如果图里有清晰可见文字，请准确抄出文字；文字不清楚就写“不清楚/无”。\\n"\n                "可见文字可以作为较可靠的视觉事实；但图片真正想表达的含义仍然必须低置信处理。\\n"\n                "不要擅自判断图片真正想表达的意思；如果要说含义，必须用“可能/像是/不确定”。\\n"\n                "如果图片没什么明确内容，就直接说信息量低，不要硬解释。\\n"\n                "按格式输出，简短中文：\\n"\n                "可见文字：逐字抄出清晰文字；没有或看不清写“无”。\\n"\n                "文字清晰度：高/中/低/无。\\n"\n                "可见内容：确定能看到的主体、表情、动作。\\n"\n                "不确定点：可能看错、需要上下文、无法确认的内容；没有就写“无明显”。\\n"\n                "可能情绪：低置信度推测，例如“可能是在调侃/疑惑/无语”；不要下定论。\\n"\n                "采信度：高/中/低。只有文字清楚、主体明确时才能高；表情包和梗图的含义通常为中或低。\\n"\n                "不要输出客套话，不要说你是模型。"\n            )\n            if user_text:\n                prompt += f"\\n用户配文：{user_text}\\n可以结合配文，但仍不要过度解读图片本意。"\n\n            payload = {\n                "model": model,\n                "temperature": 0.0,\n                "max_tokens": 420,\n                "messages": [\n                    {"role": "user", "content": [{"type": "text", "text": prompt}, image_part]}\n                ],\n            }\n\n            req = urllib.request.Request(\n                endpoint,\n                data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),\n                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},\n                method="POST",\n            )\n\n            try:\n                with urllib.request.urlopen(req, timeout=45) as resp:\n                    body = json.loads(resp.read().decode("utf-8"))\n                content = str(body["choices"][0]["message"]["content"]).strip()\n                if content:\n                    content = re.sub(r"\\s+", " ", content).strip()\n                    descriptions.append(f"第{index}张图片低采信度线索：{content}")\n            except Exception as exc:\n                descriptions.append(f"第{index}张图片识别失败：{exc}")\n\n        return descriptions\n'
STICKER_TEXT_HELPERS = '\n    def _extract_obvious_text_from_image_descriptions(self, descriptions: list[str]) -> str:\n        """从识图结果中提取清晰的表情包文字。"""\n        for desc in descriptions or []:\n            s = str(desc or "").strip()\n            if not s:\n                continue\n\n            m = re.search(r"可见文字[:：]\\s*(.*?)(?:\\s+文字清晰度[:：]|\\s+可见内容[:：]|\\s+不确定点[:：]|$)", s)\n            if not m:\n                m = re.search(r"(?:文字|图中文字)[:：]\\s*(.*?)(?:\\s+文字清晰度[:：]|\\s+可见内容[:：]|\\s+不确定点[:：]|$)", s)\n            if not m:\n                continue\n\n            text = m.group(1).strip(" \\n\\r\\t。；;，,")\n            if not text:\n                continue\n            if any(x in text for x in ("无", "没有", "看不清", "不清楚", "无法识别")) and len(text) <= 8:\n                continue\n\n            clarity = ""\n            m2 = re.search(r"文字清晰度[:：]\\s*(高|中|低|无)", s)\n            if m2:\n                clarity = m2.group(1)\n            if clarity in {"低", "无"}:\n                continue\n\n            text = re.sub(r"\\s+", "", text)\n            if 1 <= len(text) <= 40:\n                return text\n\n        return ""\n\n    def _plain_image_might_be_reply_to_self(self, chat_id: str, text: str) -> bool:\n        """纯表情包是否可能是在回应机器人刚才的话。\n\n        不代表一定回复，只是允许它绕过“纯图硬忽略”，进入 OCR 检查。\n        """\n        raw = str(text or "")\n        if "[CQ:image" not in raw:\n            return False\n\n        # 明确 reply 或 at 通常应允许后续逻辑判断。\n        if "[CQ:reply" in raw:\n            return True\n\n        try:\n            last_reply = self.last_auto_reply.get(str(chat_id))\n            if isinstance(last_reply, datetime):\n                delta = (datetime.now() - last_reply).total_seconds()\n                return 0 <= delta <= 90\n        except Exception:\n            pass\n\n        return False\n\n    def _maybe_attach_sticker_visible_text_context(\n        self,\n        chat_id: str,\n        text: str,\n        image_refs: list[str],\n        context_info: dict[str, Any] | None = None,\n    ) -> str:\n        """如果表情包里有明显文字，把它作为可见文字线索放进 context_info。\n\n        只在“可能回应机器人刚才发言”的纯图场景短暂等待 OCR；\n        其他纯图仍然只当背景。\n        """\n        context_info = context_info or {}\n        if not image_refs:\n            return ""\n\n        if not self._plain_image_might_be_reply_to_self(chat_id, text):\n            return ""\n\n        try:\n            ctx = dict(context_info)\n            ctx["explicit_image_question"] = True  # 复用等待逻辑：短暂等 OCR 出来\n            ctx["sticker_text_probe"] = True\n            if hasattr(self, "_get_image_observations"):\n                descriptions = self._get_image_observations(image_refs, text, context_info=ctx)\n            else:\n                descriptions = self._describe_images_with_qwen_vl(image_refs[:1], text)\n        except Exception:\n            descriptions = []\n\n        visible_text = self._extract_obvious_text_from_image_descriptions(descriptions)\n        if not visible_text:\n            return ""\n\n        context_info["sticker_visible_text"] = visible_text\n        context_info["image_descriptions"] = descriptions\n        context_info["image_observation_confidence"] = "text_high_meaning_low"\n        return visible_text\n'
STICKER_SHOULD_SNIPPET = '        # 表情包里有明显文字，且像是在回应机器人刚才的话：把图中文字当作候选反应。\n        try:\n            sticker_text = self._maybe_attach_sticker_visible_text_context(chat_id, text, image_refs, context_info)\n            if sticker_text:\n                context_info["reply_relevance"] = 68\n                context_info["reply_relevance_reason"] = f"表情包有清晰可见文字：{sticker_text}；像是在回应我刚才的话"\n                context_info["social_action"] = "candidate"\n                context_info["social_confidence"] = 0.56\n                context_info["social_gate_reason"] = "表情包文字可能是在回应 SELF；文字可信，含义仍需保守"\n                return False, f"表情包文字候选：{sticker_text}"\n        except Exception:\n            pass\n\n'


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


def ensure_method(src: str, method_name: str, method_text: str, before_method: str) -> str:
    if method_range(src, method_name) is not None:
        return replace_method(src, method_name, method_text)
    return insert_before(src, before_method, method_text)


def ensure_sticker_helpers(src: str) -> str:
    for name in (
        "_extract_obvious_text_from_image_descriptions",
        "_plain_image_might_be_reply_to_self",
        "_maybe_attach_sticker_visible_text_context",
    ):
        method_text = extract_one_method(STICKER_TEXT_HELPERS, name)
        if method_range(src, name) is not None:
            src = replace_method(src, name, method_text)
        else:
            target = "_should_reply_to_group_message" if method_range(src, "_should_reply_to_group_message") else "_handle_message"
            src = insert_before(src, target, method_text)
    return src


def patch_pure_image_guard(src: str) -> str:
    # 纯图硬忽略时，如果“像是在回应机器人刚才发言”，允许进入 _should_reply 做 OCR 判断。
    if "_plain_image_might_be_reply_to_self(chat_id, text)" in src:
        return src

    old = (
        "and not self._message_has_explicit_image_question(text)\n"
        "            ):"
    )
    new = (
        "and not self._message_has_explicit_image_question(text)\n"
        "                and not self._plain_image_might_be_reply_to_self(chat_id, text)\n"
        "            ):"
    )
    if old in src:
        return src.replace(old, new, 1)

    print("⚠️ 没找到纯图硬忽略条件，已跳过；表情包文字仍可在其它路径中作为视觉线索。")
    return src


def patch_should_reply_sticker_text(src: str) -> str:
    if "表情包里有明显文字，且像是在回应机器人刚才的话" in src:
        return src

    rng = method_range(src, "_should_reply_to_group_message")
    if rng is None:
        print("⚠️ 找不到 _should_reply_to_group_message，无法添加表情包文字候选逻辑。")
        return src

    start, end = rng
    lines = src.splitlines()
    method = lines[start - 1:end]

    insert_at = None
    for i, line in enumerate(method):
        if "context_info = context_info or {}" in line:
            insert_at = i + 1
            break

    if insert_at is None:
        insert_at = 1

    method[insert_at:insert_at] = STICKER_SHOULD_SNIPPET.rstrip("\n").splitlines()
    new_lines = lines[: start - 1] + method + lines[end:]
    return "\n".join(new_lines) + "\n"


def patch_prompt_text_policy(src: str) -> str:
    addition = (
        " 表情包/图片里如果有清晰可见文字，可以把“可见文字”当作图片中的文字事实；"
        "但图片真正想表达的含义仍然要低置信处理。"
        "如果清晰文字是在机器人刚发言后出现的表情包里，可以把它当作对机器人刚才话的候选反应；"
        "回复时不要自信断言，只用轻微试探/接梗语气。"
    )
    if addition in src:
        return src

    for marker in (
        "图片识别结果只当低采信度视觉线索",
        "不要输出 Markdown、标题、编号、解释性前言。",
        "回复要短，像 QQ 聊天，不要写文章。",
    ):
        if marker in src:
            return src.replace(marker, marker + addition, 1)

    return src


def main() -> None:
    if not TARGET.exists():
        raise SystemExit(f"找不到文件：{TARGET}")

    src = TARGET.read_text(encoding="utf-8")
    backup = TARGET.with_suffix(".py.bak_fragment_and_sticker_text")
    backup.write_text(src, encoding="utf-8")

    # 1. 只修主动开话题半截句，不改频率。
    src = ensure_method(
        src,
        "_proactive_topic_quality_ok",
        PROACTIVE_QUALITY,
        "_generate_proactive_topic_text" if method_range(src, "_generate_proactive_topic_text") else "_maybe_send_proactive_topic",
    )
    if method_range(src, "_generate_proactive_topic_text") is not None:
        src = replace_method(src, "_generate_proactive_topic_text", PROACTIVE_GENERATE)
    else:
        print("⚠️ 没找到 _generate_proactive_topic_text，已跳过半截句修复。")

    # 2. 识图 prompt 增加“可见文字/文字清晰度”。
    if method_range(src, "_describe_images_with_qwen_vl") is not None:
        src = replace_method(src, "_describe_images_with_qwen_vl", VISION_DESCRIBE)
    else:
        print("⚠️ 没找到 _describe_images_with_qwen_vl，已跳过表情包文字识别 prompt。")

    # 3. 表情包清晰文字：只在“像回应机器人刚才话”时进入候选。
    src = ensure_sticker_helpers(src)
    src = patch_pure_image_guard(src)
    src = patch_should_reply_sticker_text(src)
    src = patch_prompt_text_policy(src)

    compile(src, str(TARGET), "exec")
    TARGET.write_text(src, encoding="utf-8")

    print("✅ 已修复：主动开话题半截句 + 表情包清晰文字处理")
    print("1. 不改变主动开话题频率，只提高 max_tokens 并过滤半截句。")
    print("2. 识图会单独输出“可见文字/文字清晰度”。")
    print("3. 纯表情包如果像是在回应机器人刚才发言，会短暂 OCR；有清晰文字才进入候选。")
    print("4. 图片含义仍低置信，不会把梗图解释当事实。")
    print(f"备份文件：{backup}")
    print("下一步：")
    print("  python -m py_compile .\\src\\clawmini\\tools\\qq_auto_reply.py")
    print("  python app.py")


if __name__ == "__main__":
    main()
