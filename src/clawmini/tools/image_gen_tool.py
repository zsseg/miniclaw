"""文生图工具：调用千问 Wanx 模型生成图片并保存到工作区。"""

from __future__ import annotations

import json
import os
import re
import uuid
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from PIL import Image, ImageDraw, ImageFont  # type: ignore[import-not-found]

from clawmini.core.security import ensure_path_in_workspace
from clawmini.tools.base import BaseTool
from clawmini.tools.registry import tool_plugin
from clawmini.types import ToolResult


@tool_plugin("image_generation")
class ImageGenerationTool(BaseTool):
    """文生图工具：根据文本描述生成图片。

    支持两种模式：
    1. 真实模式 —— 调用千问 DashScope API (wanx2.1-t2i) 生成图片
    2. 提示词模式 —— 离线生成结构化的画面描述提示词
    """

    name = "image_generation"
    description = "根据文本描述生成图片（调用千问文生图 API），支持保存到工作区并返回预览路径"
    parameters_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "图片描述文本，应详细描述主体、场景、风格、色彩等",
            },
            "size": {
                "type": "string",
                "description": "图片尺寸，可选：1024x1024, 720x1280, 1280x720",
                "default": "1024x1024",
            },
            "style": {
                "type": "string",
                "description": "可选风格：写实(default), 二次元, 水彩, 油画, 素描, 国风",
                "default": "写实",
            },
            "n": {
                "type": "integer",
                "description": "生成图片数量（1-4）",
                "default": 1,
            },
            "filename": {
                "type": "string",
                "description": "保存文件名（不含路径，可选，自动生成）",
            },
            "title": {
                "type": "string",
                "description": "图片标题（可用于生成文件名和预览标题）",
            },
            "output_dir": {
                "type": "string",
                "description": "保存目录（工作区内相对路径或绝对路径，若提供则优先使用）",
            },
            "target_path": {
                "type": "string",
                "description": "完整目标路径（优先级最高，需位于工作区内）",
            },
        },
        "required": ["prompt"],
    }

    def __init__(self, workspace_dir: Path, api_key: str | None = None) -> None:
        super().__init__(workspace_dir)
        self._api_key = api_key
        self._output_dir = workspace_dir / "generated_images"
        self._output_dir.mkdir(parents=True, exist_ok=True)

    def set_api_key(self, api_key: str | None) -> None:
        """动态设置 API Key（可在 Agent 初始化后配置）。"""
        self._api_key = api_key

    def run(self, arguments: dict[str, Any], progress_callback: Callable[[str], None] | None = None) -> ToolResult:
        prompt = str(arguments.get("prompt", "")).strip()
        if not prompt:
            return ToolResult(success=False, output="请提供图片描述文本（prompt）")

        size = str(arguments.get("size", "1024x1024"))
        style = str(arguments.get("style", "写实"))
        n = min(int(arguments.get("n", 1)), 4)

        # 给 prompt 添加风格修饰
        target_info = self._resolve_target(arguments, prompt)
        user_filename = target_info["filename"]
        save_dir = target_info["save_dir"]
        title = target_info["title"]
        clean_prompt = target_info["clean_prompt"]
        enhanced_prompt = self._enhance_prompt(clean_prompt, style)

        # 通知用户任务开始
        if progress_callback is not None:
            progress_callback(f"🖼️ 正在准备生成图片「{title}」...")

        # 如果有 API Key，调用真实 API
        if self._api_key:
            try:
                return self._call_api(enhanced_prompt, size, n, save_dir, user_filename, title, progress_callback=progress_callback)
            except Exception as exc:
                preview_paths = self._save_prompt_preview(enhanced_prompt, save_dir, user_filename, title, reason="API 调用失败")
                return ToolResult(
                    success=False,
                    output=(
                        f"API 调用失败：{exc}\n"
                        f"已为您生成画面描述提示词：\n\n{enhanced_prompt}\n\n"
                        f"已保存本地预览文件：\n" + "\n".join(preview_paths)
                    ),
                    meta={"mode": "preview_fallback", "enhanced_prompt": enhanced_prompt, "files": preview_paths},
                )

        # 无 API Key —— 仅生成提示词
        preview_paths = self._save_prompt_preview(enhanced_prompt, save_dir, user_filename, title, reason="未配置 API Key")
        result_lines = [
            "🖼️ 画面描述（提示词模式）：",
            "",
            enhanced_prompt,
            "",
            "💡 提示：如需生成实际图片，请在 ⚙ 设置中选择真实模型并填入 API Key。",
            "也可以将上述提示词复制到其他绘图工具中使用。",
            "",
            "📁 已保存本地预览文件：",
        ]
        result_lines.extend(preview_paths)
        return ToolResult(
            success=True,
            output="\n".join(result_lines),
            meta={"mode": "prompt_only", "enhanced_prompt": enhanced_prompt, "files": preview_paths, "title": title, "save_dir": str(save_dir)},
        )

    def _sanitize_filename(self, value: str, fallback: str) -> str:
        cleaned = re.sub(r"[\\/:*?\"<>|]+", "_", value).strip()
        cleaned = re.sub(r"\s+", "_", cleaned)
        cleaned = re.sub(r"_+", "_", cleaned).strip("._")
        return cleaned or fallback

    def _resolve_target(self, arguments: dict[str, Any], prompt: str) -> dict[str, Any]:
        """解析标题、输出目录、文件名和目标路径。"""
        clean_prompt = prompt
        raw_title = str(arguments.get("title", "")).strip()
        raw_filename = str(arguments.get("filename", "")).strip()
        raw_output_dir = str(arguments.get("output_dir", "")).strip()
        raw_target_path = str(arguments.get("target_path", "")).strip()

        def _extract_segment(labels: list[str], stop_labels: list[str]) -> str:
            pattern = re.compile(rf"(?:{'|'.join(labels)})[:：]\s*", flags=re.IGNORECASE)
            match = pattern.search(prompt)
            if not match:
                return ""
            segment = prompt[match.end():]
            stop_index = len(segment)
            for stop_label in stop_labels:
                stop_pos = segment.find(stop_label)
                if stop_pos != -1:
                    stop_index = min(stop_index, stop_pos)
            value = segment[:stop_index].strip().strip('"\'')
            value = value.strip(" ,，;；:")
            return value

        if not raw_title:
            raw_title = _extract_segment(
                ["标题", "题目", "主题", "标题名", "主题名"],
                ["标题", "题目", "主题", "标题名", "主题名", "文件名", "图片名", "输出目录", "保存目录", "保存到目录", "保存到", "路径", "保存路径", "目标路径"],
            )

        if not raw_filename:
            raw_filename = _extract_segment(
                ["文件名", "图片名"],
                ["标题", "题目", "主题", "标题名", "主题名", "输出目录", "保存目录", "保存到目录", "保存到", "路径", "保存路径", "目标路径"],
            )

        if not raw_output_dir:
            raw_output_dir = _extract_segment(
                ["输出目录", "保存目录", "保存到目录"],
                ["标题", "题目", "主题", "标题名", "主题名", "文件名", "图片名", "保存到", "路径", "保存路径", "目标路径"],
            )

        if not raw_target_path:
            raw_target_path = _extract_segment(
                ["保存到", "路径", "保存路径", "目标路径"],
                ["标题", "题目", "主题", "标题名", "主题名", "文件名", "图片名", "输出目录", "保存目录", "保存到目录"],
            )

        metadata_pattern = re.compile(
            r"(?:标题|题目|主题|标题名|主题名|文件名|图片名|输出目录|保存目录|保存到目录|保存到|路径|保存路径|目标路径)[:：]",
            flags=re.IGNORECASE,
        )
        metadata_match = metadata_pattern.search(prompt)
        if metadata_match:
            clean_prompt = prompt[: metadata_match.start()].strip(" ,，;；:")
        clean_prompt = re.sub(r"\s+", " ", clean_prompt).strip()
        if not clean_prompt:
            clean_prompt = raw_title or prompt.strip()

        save_dir = self._output_dir
        filename = raw_filename
        if raw_target_path:
            candidate = Path(raw_target_path)
            if candidate.suffix:
                save_dir = candidate.parent
                filename = candidate.name
            else:
                save_dir = candidate
        elif raw_output_dir:
            save_dir = Path(raw_output_dir)

        if not save_dir.is_absolute():
            save_dir = self.workspace_dir / save_dir
        save_dir = ensure_path_in_workspace(save_dir, self.workspace_dir)
        save_dir.mkdir(parents=True, exist_ok=True)

        if not filename:
            base_name = raw_title or "image_generation"
            filename = f"{self._sanitize_filename(base_name, 'image_generation')}.png"
        elif Path(filename).suffix == "":
            filename = f"{self._sanitize_filename(filename, 'image_generation')}.png"
        else:
            filename = self._sanitize_filename(filename, "image_generation")

        title = re.sub(r"\s+", "", raw_title or Path(filename).stem) or Path(filename).stem
        return {"save_dir": save_dir, "filename": filename, "title": title, "clean_prompt": clean_prompt}

    def _save_prompt_preview(self, prompt: str, save_dir: Path, user_filename: str, title: str, reason: str) -> list[str]:
        """保存本地提示词预览文件，确保无 API 时也有可见产物。"""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        stem = Path(user_filename).stem.strip() if user_filename else ""
        stem = self._sanitize_filename(stem or title or f"image_prompt_{ts}_{uuid.uuid4().hex[:4]}", f"image_prompt_{ts}")
        txt_path = save_dir / f"{stem}.txt"
        png_path = save_dir / f"{stem}.png"

        txt_path.write_text(f"{reason}\n\n{prompt}\n", encoding="utf-8")

        canvas = Image.new("RGB", (1024, 1024), color=(243, 247, 250))
        draw = ImageDraw.Draw(canvas)
        try:
            title_font = ImageFont.truetype("arial.ttf", 28)
            body_font = ImageFont.truetype("arial.ttf", 22)
        except Exception:
            title_font = ImageFont.load_default()
            body_font = ImageFont.load_default()

        draw.text((48, 36), f"Clawmini 文生图预览 - {title}", fill=(28, 45, 56), font=title_font)
        draw.text((48, 84), reason, fill=(70, 90, 102), font=body_font)

        wrapped_lines: list[str] = []
        current = ""
        for chunk in prompt.replace("\n", " ").split(" "):
            if not chunk:
                continue
            candidate = f"{current} {chunk}".strip()
            if len(candidate) > 44:
                if current:
                    wrapped_lines.append(current)
                current = chunk
            else:
                current = candidate
        if current:
            wrapped_lines.append(current)

        y = 150
        for line in wrapped_lines[:28]:
            draw.text((48, y), line, fill=(30, 30, 30), font=body_font)
            y += 30

        draw.rounded_rectangle((40, 120, 984, 944), radius=22, outline=(188, 201, 214), width=2)
        draw.text((48, 964), f"提示词文件已保存到：{save_dir}", fill=(90, 110, 122), font=body_font)
        canvas.save(png_path)

        return [str(txt_path), str(png_path)]

    def _enhance_prompt(self, prompt: str, style: str) -> str:
        """润色并增强绘画提示词。"""
        style_map = {
            "二次元": "anime style, vibrant colors, cel shading, Japanese animation style",
            "水彩": "watercolor painting style, soft edges, flowing pigments, artistic",
            "油画": "oil painting style, rich textures, thick brushstrokes, classical",
            "素描": "sketch style, pencil drawing, black and white, fine lines",
            "国风": "Chinese traditional painting style, ink wash, elegant, classical Chinese art",
            "写实": "photorealistic, highly detailed, 8K, natural lighting, sharp focus",
        }
        style_en = style_map.get(style, "photorealistic, highly detailed")
        return f"{prompt}, {style_en}, high quality, masterpiece, best quality"

    def _extract_error_body(self, exc: urllib.error.HTTPError) -> str:
        """从 HTTPError 中提取响应体详细信息。"""
        try:
            body = exc.read().decode("utf-8", errors="replace")
            parsed = json.loads(body)
            # 提取阿里云 DashScope 错误格式
            if "message" in parsed:
                return parsed["message"]
            if "error" in parsed:
                if isinstance(parsed["error"], dict):
                    return parsed["error"].get("message", str(parsed["error"]))
                return str(parsed["error"])
            if "code" in parsed:
                msg = parsed.get("message", "")
                return f"[{parsed['code']}] {msg}".strip()
            return body[:500]
        except Exception:
            # 响应体不是 JSON 或读取失败
            return str(exc)

    def _build_access_denied_guide(self, error_text: str, title: str, save_dir: Path, enhanced_prompt: str = "", user_filename: str = "") -> str:
        """根据 API 错误生成用户友好的引导信息。"""
        is_403 = "HTTP 403" in error_text or "AccessDenied" in error_text
        is_model_not_exist = "Model not exist" in error_text

        lines = [
            f"⚠️ 通义万相 API 请求失败（当前 API Key 未开通文生图服务）。",
            f"标题：{title}",
            f"保存目录：{save_dir}",
            "",
        ]

        lines += [
            "🛠 解决方法（二选一）：",
            "",
            "方案 A：开通通义万相服务",
            "1. 打开 https://bailian.console.aliyun.com/",
            "2. 在左侧菜单找到「模型广场」→ 搜索「通义万相」",
            "3. 点击「开通服务」并同意协议",
            "4. 开通后稍等 1-2 分钟即可使用",
            "",
            "方案 B：使用其他绘图工具（已自动生成本地占位图）",
            f"将以下提示词复制到 Midjourney / Stable Diffusion 等工具生成：",
            "",
        ]

        preview_paths = self._save_prompt_preview(enhanced_prompt, save_dir, user_filename, title, reason="API 调用失败")
        lines += [
            "💡 已为您保存画面描述提示词，可复制到其他绘图工具使用：",
            "",
        ]
        lines += preview_paths
        return "\n".join(lines)

    def _call_api(
        self,
        prompt: str,
        size: str,
        n: int,
        save_dir: Path,
        user_filename: str,
        title: str,
        progress_callback: Callable[[str], None] | None = None,
    ) -> ToolResult:
        """调用千问 DashScope 文生图 API（异步任务模式）。

        百炼 Wanx 文生图 API 工作流程：
        1. POST 提交任务（含 X-DashScope-Async: enable 头）→ 获得 task_id
        2. GET /api/v1/tasks/{task_id} 轮询任务状态
        3. 成功后从 results[].url 下载图片
        """
        import time

        # 把 1024x1024 转为百炼格式 1024*1024
        api_size = size.replace("x", "*").replace("×", "*")
        if api_size.count("*") != 1:
            api_size = "1024*1024"

        wanx_models = [
            "wanx2.1-t2i-plus",
            "wanx2.1-t2i",
        ]

        task_endpoint = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text2image/image-synthesis"
        poll_endpoint_prefix = "https://dashscope.aliyuncs.com/api/v1/tasks/"

        last_error = ""
        for model_name in wanx_models:
            task_payload = {
                "model": model_name,
                "input": {"prompt": prompt},
                "parameters": {"size": api_size, "n": n},
            }
            data = json.dumps(task_payload, ensure_ascii=False).encode("utf-8")
            try:
                req = urllib.request.Request(
                    task_endpoint,
                    data=data,
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                        "X-DashScope-Async": "enable",
                    },
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=30) as resp:
                    result = json.loads(resp.read().decode("utf-8"))
                task_id = result.get("output", {}).get("task_id", "")
                if not task_id:
                    last_error = f"[{model_name}] 提交任务后未获取到 task_id: {json.dumps(result, ensure_ascii=False)[:300]}"
                    continue

                # 轮询任务结果
                for poll_round in range(60):
                    time.sleep(2)
                    poll_req = urllib.request.Request(
                        f"{poll_endpoint_prefix}{task_id}",
                        headers={"Authorization": f"Bearer {self._api_key}"},
                    )
                    with urllib.request.urlopen(poll_req, timeout=10) as poll_resp:
                        status = json.loads(poll_resp.read().decode("utf-8"))
                    task_status = status.get("output", {}).get("task_status", "")

                    if task_status == "SUCCEEDED":
                        # 提取图片 URL
                        results = status.get("output", {}).get("results", [])
                        image_urls: list[str] = []
                        for item in results:
                            url = str(item.get("url", "")).strip()
                            if url:
                                image_urls.append(url)
                        if not image_urls:
                            last_error = f"[{model_name}] 任务完成但无图片 URL: {json.dumps(status, ensure_ascii=False)[:300]}"
                            break

                        if progress_callback is not None:
                            progress_callback("📥 任务完成，正在下载图片...")
                        saved_result = self._save_images(image_urls, save_dir, user_filename)
                        if saved_result["success"]:
                            result_lines = [
                                f"✅ 成功生成 {saved_result['count']} 张图片！",
                                f"模型：{model_name}",
                                f"标题：{title}",
                                f"保存目录：{save_dir}",
                                "",
                            ]
                            result_lines.extend(saved_result["paths"])
                            return ToolResult(
                                success=True,
                                output="\n".join(result_lines),
                                meta={
                                    "mode": f"dashscope_async_{model_name}",
                                    "saved_paths": saved_result["paths"],
                                    "count": saved_result["count"],
                                    "prompt": prompt,
                                    "save_dir": str(save_dir),
                                    "title": title,
                                },
                            )
                        last_error = saved_result["error"]
                        break

                    elif task_status in ("FAILED",):
                        code = status.get("output", {}).get("code", "")
                        msg = status.get("output", {}).get("message", "")
                        last_error = f"[{model_name}] 任务失败: [{code}] {msg}"
                        break
                    elif task_status in ("CANCELED",):
                        last_error = f"[{model_name}] 任务被取消"
                        break
                    # else RUNNING → 每10轮发一次进度
                    if progress_callback is not None and poll_round % 10 == 0 and poll_round > 0:
                        progress_callback(f"⏳ 图片生成中...（已等待 {poll_round * 2} 秒）")
                else:
                    last_error = f"[{model_name}] 轮询超时（120秒）"

            except urllib.error.HTTPError as exc:
                detail = self._extract_error_body(exc)
                last_error = f"[{model_name}] HTTP {exc.code}: {detail}"
                if exc.code == 403:
                    break  # 403 权限不足，不再尝试其他模型
                continue
            except urllib.error.URLError as exc:
                preview_paths = self._save_prompt_preview(prompt, save_dir, user_filename, title, reason="网络请求失败")
                return ToolResult(
                    success=True,
                    output=(
                        f"❌ 网络请求失败，请检查网络连接：{exc.reason}\n"
                        f"标题：{title}\n保存目录：{save_dir}\n"
                        f"已保存本地预览文件：\n" + "\n".join(preview_paths)
                    ),
                    meta={"mode": "network_error", "save_dir": str(save_dir), "title": title, "files": preview_paths},
                )

        # 所有模型都失败 → 生成本地占位图
        local_img_path = self._generate_local_fallback(prompt, save_dir, user_filename, title)
        preview_paths = self._save_prompt_preview(prompt, save_dir, user_filename, title, reason="API 调用失败")
        all_files = list(preview_paths)
        if local_img_path:
            all_files.append(local_img_path)

        guide_lines = [
            f"⚠️ 通义万相 API 请求失败：{last_error}",
            f"标题：{title}",
            f"保存目录：{save_dir}",
            "",
            "🛠 排查建议：",
            "1. 确认已开通通义万相服务：https://bailian.console.aliyun.com/ → 模型广场 → 通义万相",
            f"2. 确认 API Key 有权限（当前 Key: ...{self._api_key[-8:] if self._api_key and len(self._api_key) > 8 else ''}）",
            "3. 尝试更换模型：wanx2.1-t2i-plus、wanx2.1-t2i",
            "",
            "💡 已保存本地预览文件：",
        ]
        guide_lines.extend(all_files)
        return ToolResult(
            success=True,
            output="\n".join(guide_lines),
            meta={
                "mode": "api_fallback",
                "save_dir": str(save_dir),
                "title": title,
                "files": all_files,
                "error": last_error,
                "local_fallback": local_img_path or "",
            },
        )

    def _extract_image_urls(self, body: dict[str, Any]) -> list[str]:
        """从返回体中提取图片 URL 或 base64 数据。"""
        image_urls: list[str] = []

        if "data" in body and isinstance(body["data"], list):
            for item in body["data"]:
                if not isinstance(item, dict):
                    continue
                url = str(item.get("url", "") or item.get("image_url", "")).strip()
                if url:
                    image_urls.append(url)
                b64 = str(item.get("b64_json", "") or item.get("base64", "")).strip()
                if b64 and not url:
                    image_urls.append(f"data:image/png;base64,{b64}")

        output = body.get("output")
        if isinstance(output, dict):
            if isinstance(output.get("results"), list):
                for item in output.get("results", []):
                    if not isinstance(item, dict):
                        continue
                    url = str(item.get("url", "") or item.get("image_url", "")).strip()
                    if url:
                        image_urls.append(url)
                    b64 = str(item.get("b64_json", "") or item.get("base64", "")).strip()
                    if b64 and not url:
                        image_urls.append(f"data:image/png;base64,{b64}")
            url = str(output.get("url", "") or output.get("image_url", "")).strip()
            if url:
                image_urls.append(url)
            b64 = str(output.get("b64_json", "") or output.get("base64", "")).strip()
            if b64 and not url:
                image_urls.append(f"data:image/png;base64,{b64}")

        if not image_urls and isinstance(body.get("result"), dict):
            result = body.get("result")
            url = str(result.get("url", "") or result.get("image_url", "")).strip()
            if url:
                image_urls.append(url)

        return image_urls

    def _save_images(self, image_urls: list[str], save_dir: Path, user_filename: str) -> dict[str, Any]:
        """下载并保存图片。"""
        saved_paths: list[str] = []
        for idx, img_url in enumerate(image_urls):
            if img_url.startswith("data:"):
                import base64

                b64_data = img_url.split(",", 1)[1]
                ext = ".png"
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                fname = user_filename or f"gen_img_{ts}_{uuid.uuid4().hex[:4]}_{idx + 1}{ext}"
                save_path = save_dir / fname
                try:
                    img_bytes = base64.b64decode(b64_data)
                    save_path.write_bytes(img_bytes)
                    saved_paths.append(str(save_path))
                except Exception as exc:
                    return {"success": False, "error": f"保存 base64 图片失败：{exc}"}
            else:
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                ext = ".png"
                fname = user_filename or f"gen_img_{ts}_{uuid.uuid4().hex[:4]}_{idx + 1}{ext}"
                save_path = save_dir / fname
                try:
                    urllib.request.urlretrieve(img_url, str(save_path))
                    saved_paths.append(str(save_path))
                except Exception as exc:
                    return {"success": False, "error": f"下载图片失败：{exc}"}

        return {"success": True, "paths": saved_paths, "count": len(saved_paths)}

    def _generate_local_fallback(self, prompt: str, save_dir: Path, user_filename: str, title: str) -> str | None:
        """当 API 不可用时，根据提示词在本地绘制一幅简单的占位图片并保存。"""
        if not user_filename:
            return None
        ext = Path(user_filename).suffix.lower()
        if ext not in (".jpg", ".jpeg", ".png", ".webp"):
            return None
        try:
            # 尝试从提示词中提取关键主题用于生成简单图形
            canvas = Image.new("RGB", (1024, 1024), color=(135, 206, 235))  # 天空蓝
            draw = ImageDraw.Draw(canvas)

            # 草地
            draw.rectangle((0, 600, 1024, 1024), fill=(34, 139, 34))
            # 太阳
            draw.ellipse((800, 80, 930, 210), fill=(255, 215, 0))
            # 几朵云
            draw.ellipse((150, 100, 280, 190), fill=(255, 255, 255))
            draw.ellipse((180, 80, 310, 170), fill=(255, 255, 255))
            draw.ellipse((500, 120, 610, 200), fill=(255, 255, 255))

            # 绘制小猪（Google Emoji 风格：粉色、圆润、简单）
            body_color = (255, 182, 193)  # 粉红
            # 身体
            draw.ellipse((400, 520, 620, 720), fill=body_color, outline=(200, 120, 140), width=3)
            # 头
            draw.ellipse((420, 400, 600, 560), fill=body_color, outline=(200, 120, 140), width=3)
            # 耳朵
            draw.ellipse((430, 380, 470, 440), fill=body_color, outline=(200, 120, 140), width=2)
            draw.ellipse((550, 380, 590, 440), fill=body_color, outline=(200, 120, 140), width=2)
            # 眼睛
            draw.ellipse((470, 450, 495, 475), fill=(0, 0, 0))
            draw.ellipse((530, 450, 555, 475), fill=(0, 0, 0))
            # 鼻孔
            draw.ellipse((490, 500, 505, 515), fill=(200, 120, 140))
            draw.ellipse((515, 500, 530, 515), fill=(200, 120, 140))
            # 嘴巴（微笑）
            draw.arc((480, 500, 540, 530), start=0, end=180, fill=(200, 120, 140), width=2)
            # 腿
            draw.rounded_rectangle((430, 710, 460, 770), radius=8, fill=body_color, outline=(200, 120, 140), width=2)
            draw.rounded_rectangle((560, 710, 590, 770), radius=8, fill=body_color, outline=(200, 120, 140), width=2)
            draw.rounded_rectangle((470, 715, 495, 770), radius=8, fill=body_color, outline=(200, 120, 140), width=2)
            draw.rounded_rectangle((525, 715, 550, 770), radius=8, fill=body_color, outline=(200, 120, 140), width=2)
            # 尾巴（小卷）
            draw.arc((610, 580, 640, 610), start=270, end=450, fill=(200, 120, 140), width=3)

            # 添加文字说明
            try:
                font = ImageFont.truetype("arial.ttf", 20)
            except Exception:
                font = ImageFont.load_default()
            draw.text((20, 980), f"Local preview: {title}", fill=(255, 255, 255), font=font)

            save_path = save_dir / user_filename
            # 如果用户指定 .jpg 则用 RGB 模式保存
            canvas.save(save_path, quality=85)
            return str(save_path)
        except Exception:
            return None
