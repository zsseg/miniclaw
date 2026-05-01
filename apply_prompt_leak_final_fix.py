#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""最终修复 prompt 泄漏：清理图片管线 + 清理兜底回复 + 发送前强制过滤。

你这次日志里的真正泄漏格式是：
    [custom_prompt] 收到：[CQ:image...]. 建议你先确认需求细节...
这说明不是 Qwen-VL 没识别，而是 DeepSeek 400 后走了旧的本地兜底回复；
旧兜底把 custom_prompt 拼进了回复，而且 _send_via_gateway 没有最终过滤。
"""

from __future__ import annotations

import ast
import re
from pathlib import Path


PROJECT_ROOT = Path.cwd()
TARGET = PROJECT_ROOT / "src" / "clawmini" / "tools" / "qq_auto_reply.py"

NEW_BUILD_USER_CONTENT = '\n    def _build_user_content(self, text: str, context_info: dict[str, Any]) -> str | list[dict[str, Any]]:\n        """构造发给回复模型的用户内容。\n\n        修复点：\n        - 不再把“请识别图片 / 请基于图片回复 / 〖图片内容解析〗”这类中间 prompt 放进最终输入。\n        - DeepSeek 不吃图时，只把 Qwen-VL 的“图片事实描述”交给 DeepSeek。\n        - 原始 CQ:image 不再进入 base_text，避免接口失败时被兜底回复原样发出。\n        """\n        image_refs: list[str] = []\n        seen_refs: set[str] = set()\n\n        for item in context_info.get("image_refs", []):\n            ref = str(item).strip()\n            if not ref or ref in seen_refs:\n                continue\n            seen_refs.add(ref)\n            image_refs.append(ref)\n\n        def _clean_user_text_for_image(raw: str) -> str:\n            cleaned = str(raw or "")\n            cleaned = re.sub(r"\\[CQ:image[^\\]]*\\]", "", cleaned)\n            cleaned = re.sub(r"\\[CQ:at[^\\]]*\\]", "", cleaned)\n            cleaned = cleaned.replace("[图片]", "").replace("图片消息", "")\n            cleaned = re.sub(r"\\s+", " ", cleaned).strip()\n            return cleaned\n\n        if self.enable_image_recognition and image_refs:\n            provider = self.reply_api_provider.strip().lower()\n            base_text = _clean_user_text_for_image(text)\n\n            if provider == "deepseek":\n                descriptions = self._describe_images_with_qwen_vl(image_refs, base_text)\n\n                clean_descriptions: list[str] = []\n                forbidden_bits = [\n                    "请识别这张 QQ 聊天图片",\n                    "如果是表情包/梗图",\n                    "如果是截图",\n                    "如果是普通图片",\n                    "用中文回答，直接描述图片内容，不要客套",\n                    "用户配文：",\n                    "请基于上面的图片内容",\n                    "请自然说明你暂时没看清图片",\n                    "〖图片内容解析",\n                    "〖图片提示〗",\n                    "来自 Qwen-VL",\n                ]\n\n                for item in descriptions:\n                    desc = str(item or "").strip()\n                    if not desc:\n                        continue\n                    if "识别失败" in desc:\n                        continue\n                    if any(bit in desc for bit in forbidden_bits):\n                        continue\n                    clean_descriptions.append(desc)\n\n                if clean_descriptions:\n                    image_block = "\\n".join(f"- {item}" for item in clean_descriptions)\n                    if base_text:\n                        return f"{base_text}\\n\\n图片内容：\\n{image_block}"\n                    return f"用户发送了图片。\\n\\n图片内容：\\n{image_block}"\n\n                if base_text:\n                    return f"{base_text}\\n\\n图片内容：暂时无法识别清楚。"\n                return "用户发送了一张图片，但图片内容暂时无法识别清楚。"\n\n            image_hints: list[str] = []\n            for ref in image_refs:\n                img_type = self._classify_image_type(ref)\n                image_hints.append(f"[附带的{img_type}]")\n\n            annotated_text = base_text or "用户发送了图片。"\n            if image_hints:\n                annotated_text = annotated_text + "\\n\\n图片附件：" + "；".join(image_hints)\n\n            content: list[dict[str, Any]] = [{"type": "text", "text": annotated_text}]\n            for ref in image_refs:\n                image_part = self._image_ref_to_content_part(ref)\n                if image_part is not None:\n                    content.append(image_part)\n\n            if len(content) > 1:\n                return content\n\n            return annotated_text\n\n        return text\n'
NEW_SANITIZER = '\n    def _sanitize_reply_before_send(self, reply: str) -> str:\n        """发送前最终防线：禁止把人设 prompt、识图 prompt、CQ 原文发到 QQ。"""\n        text = str(reply or "").strip()\n        if not text:\n            return ""\n\n        custom_prompt = str(getattr(self, "custom_prompt", "") or "").strip()\n\n        def _safe_fallback() -> str:\n            return "刚才接口有点抽风，猫猫先不乱说喵。"\n\n        # 自定义人设整段泄漏，典型形式：[你现在的人设是...]\n        if custom_prompt and len(custom_prompt) >= 20:\n            if custom_prompt[:20] in text or f"[{custom_prompt[:20]}" in text:\n                return _safe_fallback()\n\n        prompt_keywords = [\n            "你现在的人设",\n            "系统提示",\n            "system prompt",\n            "### 人设",\n            "### 回复风格",\n            "### 当前上下文",\n            "不要输出 Markdown",\n            "不要逐条回复",\n            "你的任务不是逐条回复",\n            "请识别这张 QQ 聊天图片",\n            "如果是表情包/梗图",\n            "如果是截图，请提取关键文字",\n            "如果是普通图片，请描述主体",\n            "用中文回答，直接描述图片内容，不要客套",\n            "请基于上面的图片内容",\n            "请自然说明你暂时没看清图片",\n            "〖图片内容解析",\n            "〖图片提示〗",\n            "来自 Qwen-VL",\n            "用户配文：",\n            "建议你先确认需求细节，我可以继续协助",\n        ]\n\n        if any(key in text for key in prompt_keywords):\n            # 如果泄漏文本里混有真正图片描述，尽量保留图片描述；否则直接安全兜底。\n            extracted: list[str] = []\n            for raw_line in text.splitlines():\n                line = raw_line.strip().lstrip("-•* ").strip()\n                if not line:\n                    continue\n                if any(key in line for key in prompt_keywords):\n                    continue\n                if line.startswith("[") and "人设" in line:\n                    continue\n\n                if "张图片：" in line:\n                    desc = line.split("张图片：", 1)[-1].strip()\n                    if desc and not any(key in desc for key in prompt_keywords):\n                        extracted.append(desc)\n                elif line.startswith("图片内容："):\n                    desc = line.split("：", 1)[-1].strip()\n                    if desc and not any(key in desc for key in prompt_keywords):\n                        extracted.append(desc)\n                elif len(line) >= 8 and "识别失败" not in line and "[CQ:" not in line:\n                    extracted.append(line)\n\n            if extracted:\n                desc = "；".join(extracted)\n                desc = re.sub(r"\\s+", " ", desc).strip()[:180].rstrip()\n                if desc:\n                    return f"我看了下，{desc}"\n\n            return _safe_fallback()\n\n        # 不允许把 CQ 图片原文当回复发出去\n        if "[CQ:image" in text:\n            text = re.sub(r"\\[CQ:image[^\\]]*\\]", "这张图", text).strip()\n            if len(text) > 120:\n                text = "这张图我收到了，不过接口刚才有点抽风喵。"\n\n        # 清理旧兜底格式：[prompt] 收到：xxx。建议...\n        text = re.sub(r"^\\[[\\s\\S]{20,800}\\]\\s*收到：", "收到：", text).strip()\n        text = text.replace("建议你先确认需求细节，我可以继续协助。", "").strip()\n\n        for prefix in ("回复：", "回复:", "答：", "答:"):\n            if text.startswith(prefix):\n                text = text[len(prefix):].strip()\n\n        return text[:500].strip()\n'
NEW_SEND_VIA_GATEWAY = '\n    def _send_via_gateway(self, chat_id: str, reply: str, message_type: str = "group") -> ToolResult:\n        """通过网关发送文本。所有文本在这里做最后一次安全过滤。"""\n        reply = self._sanitize_reply_before_send(reply)\n        if not reply:\n            return ToolResult(False, "回复为空或被安全过滤，已阻止发送。")\n\n        if self.gateway_mode == "managed":\n            self._refresh_managed_gateway_config()\n\n        try:\n            self.gateway.send_text(chat_id=chat_id, text=reply, message_type=message_type)\n            gateway_result = getattr(self.gateway, "last_send_result", None)\n            meta: dict[str, Any] = {"chat_id": chat_id, "message_type": message_type, "reply": reply}\n\n            if isinstance(gateway_result, dict):\n                meta.update(gateway_result)\n\n                if not gateway_result.get("success", True) and self._gateway_result_is_unauthorized(gateway_result):\n                    refreshed = self._refresh_managed_gateway_config(force=True)\n                    if refreshed:\n                        self.gateway.send_text(chat_id=chat_id, text=reply, message_type=message_type)\n                        retry_result = getattr(self.gateway, "last_send_result", None)\n                        if isinstance(retry_result, dict):\n                            meta.update(retry_result)\n                            meta["retried_after_refresh"] = True\n                            if retry_result.get("success", True):\n                                meta["reply"] = reply\n                                return ToolResult(True, "ok", meta)\n                            if self._gateway_result_is_unauthorized(retry_result):\n                                meta["reply"] = reply\n                                return ToolResult(False, "NapCat 返回 Unauthorized：请检查 managed_access_token 是否与 NapCat 当前 API token 一致。", meta)\n                            meta["reply"] = reply\n                            return ToolResult(False, f"网关发送失败：{retry_result.get(\'reason\', retry_result.get(\'response\', \'未知错误\'))}", meta)\n\n                if not gateway_result.get("success", True):\n                    reason = str(gateway_result.get("reason", "发送失败"))\n                    if self._gateway_result_is_unauthorized(gateway_result):\n                        meta["reply"] = reply\n                        return ToolResult(False, "NapCat 返回 Unauthorized：请检查 managed_access_token 是否与 NapCat 当前 API token 一致。", meta)\n                    meta["reply"] = reply\n                    return ToolResult(False, f"网关发送失败：{reason}", meta)\n\n            meta["reply"] = reply\n            return ToolResult(True, "ok", meta)\n\n        except NotImplementedError as exc:\n            return ToolResult(False, f"当前网关暂不支持真实发送：{exc}。可切换网关模式为 managed（托管账号）或 mock。")\n        except Exception as exc:  # noqa: BLE001\n            return ToolResult(False, f"网关发送失败：{exc}")\n'


def find_method_range(src: str, method_name: str) -> tuple[int, int] | None:
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == method_name:
            if node.end_lineno is None:
                raise RuntimeError("当前 Python AST 没有 end_lineno，无法安全替换。")
            return node.lineno, node.end_lineno
    return None


def replace_method(src: str, method_name: str, new_method: str) -> str:
    rng = find_method_range(src, method_name)
    if rng is None:
        raise RuntimeError(f"找不到方法：{method_name}")
    start, end = rng
    lines = src.splitlines()
    new_lines = lines[: start - 1] + new_method.strip("\n").splitlines() + lines[end:]
    return "\n".join(new_lines) + "\n"


def patch_old_fallback_text(src: str) -> str:
    """把旧兜底里拼 custom_prompt 的逻辑直接废掉。"""
    src = re.sub(
        r'(?m)^(\s*)prompt_tag\s*=\s*f"\[\{self\.custom_prompt\}\]\s*"\s*if\s*self\.custom_prompt\s*else\s*""\s*$',
        r'\1prompt_tag = ""',
        src,
    )
    src = src.replace(
        'reply = f"{prompt_tag}收到：{clean_text[:120]}。建议你先确认需求细节，我可以继续协助。"',
        'reply = f"接口刚才有点抽风，猫猫先不乱说喵。"'
    )
    src = src.replace(
        'reply = f"{prompt_tag}收到：{clean_text[:120]}。我先简单接一下，等接口恢复后再认真回。"',
        'reply = f"接口刚才有点抽风，猫猫先不乱说喵。"'
    )
    src = src.replace("建议你先确认需求细节，我可以继续协助。", "")
    return src


def patch_sent_parts_logging(src: str) -> str:
    """让日志/ToolResult 里的 sent_parts 也尽量用过滤后的文本，避免 UI 继续显示泄漏。"""
    src = src.replace(
        "sent_parts = [reply_parts[0]]",
        "sent_parts = [self._sanitize_reply_before_send(reply_parts[0])]",
    )
    src = src.replace(
        "sent_parts.append(extra_part)",
        "sent_parts.append(self._sanitize_reply_before_send(extra_part))",
    )
    return src


def main() -> None:
    if not TARGET.exists():
        raise SystemExit(f"找不到文件：{TARGET}")

    src = TARGET.read_text(encoding="utf-8")
    backup = TARGET.with_suffix(".py.bak_prompt_leak_final")
    backup.write_text(src, encoding="utf-8")

    src = replace_method(src, "_build_user_content", NEW_BUILD_USER_CONTENT)
    src = replace_method(src, "_sanitize_reply_before_send", NEW_SANITIZER)
    src = replace_method(src, "_send_via_gateway", NEW_SEND_VIA_GATEWAY)
    src = patch_old_fallback_text(src)
    src = patch_sent_parts_logging(src)

    compile(src, str(TARGET), "exec")
    TARGET.write_text(src, encoding="utf-8")

    print("✅ 已完成最终修复：DeepSeek 400 后不会再把 custom_prompt / CQ:image / 识图 prompt 发群里")
    print(f"备份文件：{backup}")
    print("下一步：")
    print("  python -m py_compile .\\src\\clawmini\\tools\\qq_auto_reply.py")
    print("  python app.py")


if __name__ == "__main__":
    main()
