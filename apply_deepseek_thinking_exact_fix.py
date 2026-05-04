#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import ast
from pathlib import Path


PROJECT_ROOT = Path.cwd()
TARGET = PROJECT_ROOT / "src" / "clawmini" / "tools" / "qq_auto_reply.py"

NEW_BUILD_USER_CONTENT = '\n    def _build_user_content(self, text: str, context_info: dict[str, Any]) -> str | list[dict[str, Any]]:\n        image_refs: list[str] = []\n        seen_refs: set[str] = set()\n\n        for item in context_info.get("image_refs", []):\n            ref = str(item).strip()\n            if not ref or ref in seen_refs:\n                continue\n            seen_refs.add(ref)\n            image_refs.append(ref)\n\n        def _clean_user_text_for_image(raw: str) -> str:\n            cleaned = str(raw or "")\n            cleaned = re.sub(r"\\[CQ:image[^\\]]*\\]", "", cleaned)\n            cleaned = re.sub(r"\\[CQ:at[^\\]]*\\]", "", cleaned)\n            cleaned = cleaned.replace("[图片]", "").replace("图片消息", "")\n            cleaned = re.sub(r"\\s+", " ", cleaned).strip()\n            return cleaned\n\n        if self.enable_image_recognition and image_refs:\n            provider = self.reply_api_provider.strip().lower()\n            base_text = _clean_user_text_for_image(text)\n\n            if provider == "deepseek":\n                descriptions = self._describe_images_with_qwen_vl(image_refs, base_text)\n                clean_descriptions: list[str] = []\n                forbidden_bits = [\n                    "请识别这张 QQ 聊天图片",\n                    "如果是表情包/梗图",\n                    "如果是截图",\n                    "如果是普通图片",\n                    "用中文回答，直接描述图片内容，不要客套",\n                    "用户配文：",\n                    "请基于上面的图片内容",\n                    "请自然说明你暂时没看清图片",\n                    "【图片内容解析",\n                    "〖图片内容解析",\n                    "【图片提示】",\n                    "〖图片提示〗",\n                    "来自 Qwen-VL",\n                ]\n\n                for item in descriptions:\n                    desc = str(item or "").strip()\n                    if not desc:\n                        continue\n                    if "识别失败" in desc:\n                        continue\n                    if any(bit in desc for bit in forbidden_bits):\n                        continue\n                    clean_descriptions.append(desc)\n\n                if clean_descriptions:\n                    image_block = "\\n".join(f"- {item}" for item in clean_descriptions)\n                    if base_text:\n                        return f"{base_text}\\n\\n图片内容：\\n{image_block}"\n                    return f"用户发送了图片。\\n\\n图片内容：\\n{image_block}"\n\n                if base_text:\n                    return f"{base_text}\\n\\n图片内容：暂时无法识别清楚。"\n                return "用户发送了一张图片，但图片内容暂时无法识别清楚。"\n\n            image_hints: list[str] = []\n            for ref in image_refs:\n                img_type = self._classify_image_type(ref)\n                image_hints.append(f"[附带的{img_type}]")\n\n            annotated_text = base_text or "用户发送了图片。"\n            if image_hints:\n                annotated_text = annotated_text + "\\n\\n图片附件：" + "；".join(image_hints)\n\n            content: list[dict[str, Any]] = [{"type": "text", "text": annotated_text}]\n            for ref in image_refs:\n                image_part = self._image_ref_to_content_part(ref)\n                if image_part is not None:\n                    content.append(image_part)\n\n            if len(content) > 1:\n                return content\n\n            return annotated_text\n\n        return text\n'
OLD_EXCEPT = '        except Exception as exc:\n            self.last_reply_api_error = str(exc)\n            print("DeepSeek 请求失败：", exc)\n            return None'
NEW_EXCEPT = '        except urllib.error.HTTPError as exc:\n            body = exc.read().decode("utf-8", errors="replace")\n            self.last_reply_api_error = f"HTTP {exc.code} {exc.reason} | {body[:2000]}"\n            print("DeepSeek 请求失败：", self.last_reply_api_error)\n            return None\n        except Exception as exc:\n            self.last_reply_api_error = str(exc)\n            print("DeepSeek 请求失败：", exc)\n            return None'


def method_range(src: str, method_name: str) -> tuple[int, int]:
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == method_name:
            if node.end_lineno is None:
                raise RuntimeError("AST 没有 end_lineno")
            return node.lineno, node.end_lineno
    raise RuntimeError(f"找不到方法：{method_name}")


def replace_method(src: str, method_name: str, new_method: str) -> str:
    start, end = method_range(src, method_name)
    lines = src.splitlines()
    new_lines = lines[: start - 1] + new_method.strip("\n").splitlines() + lines[end:]
    return "\n".join(new_lines) + "\n"


def add_urllib_error_import(src: str) -> str:
    if "import urllib.error" in src:
        return src
    if "import urllib.request" in src:
        return src.replace("import urllib.request", "import urllib.request\nimport urllib.error", 1)
    return "import urllib.error\n" + src


def remove_deepseek_patch_from_qwen_vl(src: str) -> str:
    start, end = method_range(src, "_describe_images_with_qwen_vl")
    lines = src.splitlines()
    out = []
    i = 0
    while i < len(lines):
        in_method = (start - 1) <= i < end
        line = lines[i]
        stripped = line.strip()

        if in_method and stripped == "# DeepSeek V4 thinking mode: enabled":
            i += 1
            while i < len(lines) and "data = json.dumps(payload" not in lines[i]:
                i += 1
            continue

        if in_method and (
            'payload["thinking"]' in stripped
            or "payload['thinking']" in stripped
            or 'payload["reasoning_effort"]' in stripped
            or "payload['reasoning_effort']" in stripped
        ):
            i += 1
            continue

        out.append(line)
        i += 1

    return "\n".join(out) + "\n"


def patch_generate_reply_via_api(src: str) -> str:
    start, end = method_range(src, "_generate_reply_via_api")
    lines = src.splitlines()
    method_lines = lines[start - 1:end]

    cleaned = []
    i = 0
    while i < len(method_lines):
        line = method_lines[i]
        stripped = line.strip()
        if stripped.startswith('if provider == "deepseek" and model_name.startswith("deepseek-v4")'):
            base_indent = len(line) - len(line.lstrip())
            i += 1
            while i < len(method_lines):
                next_line = method_lines[i]
                next_stripped = next_line.strip()
                next_indent = len(next_line) - len(next_line.lstrip())
                if next_stripped and next_indent <= base_indent:
                    break
                i += 1
            continue
        cleaned.append(line)
        i += 1

    patched = []
    inserted = False
    for line in cleaned:
        if not inserted and "data = json.dumps(payload" in line:
            indent = line[: len(line) - len(line.lstrip())]
            patched.extend([
                f'{indent}if provider == "deepseek" and model_name.startswith("deepseek-v4"):',
                f'{indent}    payload["thinking"] = {{"type": "enabled"}}',
                f'{indent}    payload["reasoning_effort"] = "high"',
                f'{indent}    for _deepseek_bad_key in ("temperature", "top_p", "presence_penalty", "frequency_penalty", "enable_search", "search", "web_search"):',
                f'{indent}        payload.pop(_deepseek_bad_key, None)',
                f'{indent}    try:',
                f'{indent}        _max_tokens = int(payload.get("max_tokens", 0) or 0)',
                f'{indent}    except Exception:',
                f'{indent}        _max_tokens = 0',
                f'{indent}    if _max_tokens < 500:',
                f'{indent}        payload["max_tokens"] = 500',
                f'{indent}    for _msg in payload.get("messages", []):',
                f'{indent}        if isinstance(_msg, dict) and isinstance(_msg.get("content"), list):',
                f'{indent}            _parts = []',
                f'{indent}            for _part in _msg.get("content", []):',
                f'{indent}                if isinstance(_part, dict) and _part.get("type") == "text":',
                f'{indent}                    _parts.append(str(_part.get("text", "") or ""))',
                f'{indent}                elif isinstance(_part, dict) and str(_part.get("type", "")).lower() in {{"image_url", "input_image"}}:',
                f'{indent}                    _parts.append("[图片]")',
                f'{indent}            _msg["content"] = "\\n".join(_parts).strip() or "[图片]"',
            ])
            inserted = True
        patched.append(line)

    if not inserted:
        raise RuntimeError("_generate_reply_via_api 中没找到 data = json.dumps(payload...)")

    new_method_text = "\n".join(patched)
    if OLD_EXCEPT in new_method_text:
        new_method_text = new_method_text.replace(OLD_EXCEPT, NEW_EXCEPT, 1)

    all_lines = src.splitlines()
    new_lines = all_lines[: start - 1] + new_method_text.splitlines() + all_lines[end:]
    return "\n".join(new_lines) + "\n"


def main() -> None:
    if not TARGET.exists():
        raise SystemExit(f"找不到文件：{TARGET}")

    src = TARGET.read_text(encoding="utf-8")
    backup = TARGET.with_suffix(".py.bak_deepseek_thinking_exact")
    backup.write_text(src, encoding="utf-8")

    src = add_urllib_error_import(src)
    src = remove_deepseek_patch_from_qwen_vl(src)
    src = replace_method(src, "_build_user_content", NEW_BUILD_USER_CONTENT)
    src = patch_generate_reply_via_api(src)

    compile(src, str(TARGET), "exec")
    TARGET.write_text(src, encoding="utf-8")

    print("✅ 已按当前 qq_auto_reply.py 定点修复 DeepSeek Thinking")
    print("修复：Qwen-VL 不再带 thinking；DeepSeek 主回复启用 thinking；HTTP 400 会打印 body。")
    print(f"备份文件：{backup}")
    print("下一步：")
    print("  python -m py_compile .\\src\\clawmini\\tools\\qq_auto_reply.py")
    print("  python app.py")


if __name__ == "__main__":
    main()
