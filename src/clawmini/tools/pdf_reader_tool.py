"""PDF 智能阅读与处理工具。

核心能力：
1. 读取 PDF（支持扫描版 + 文字版），提取/识别内容
2. 调用 LLM 视觉 API 理解页面内容
3. 自动推理：基于内容自主决定处理方式（总结/md/出题/PPT/脑图等）
"""

from __future__ import annotations

import base64
import json
import os
import re
import time
import uuid
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from clawmini.tools.base import BaseTool
from clawmini.types import ToolResult

# 中文章节关键词 → PDF页码的缓存（生命周期内避免重复扫描）
_chapter_cache: dict[str, dict] = {}

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None


class PdfReaderTool(BaseTool):
    """PDF 智能阅读与处理工具：读取扫描/文字 PDF，自动推理并生成结果。"""

    name = "pdf_reader"
    description = (
        "PDF 智能阅读工具：支持文字/扫描版 PDF。"
        "可总结、写笔记、出题、生成 PPT/PDF 等。"
        "自动推理要做什么操作，无需手动指定。"
    )
    parameters_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "操作类型：read(智能读取并自动处理) / info(查询PDF信息)",
            },
            "pdf_path": {
                "type": "string",
                "description": "PDF 文件路径（工作区内路径或绝对路径）",
            },
            "page_range": {
                "type": "string",
                "description": "页码范围，如 '3'（单页）、'3-5'（多页）、'1,3,5'（不连续页）。不传则默认全pdf（但建议指定范围，例如第三章第一节）",
            },
            "instruction": {
                "type": "string",
                "description": "可选的额外指令。不传时工具自动推理要做什么（如总结、写笔记、出题、生成PPT等）。传入指令可控制输出方式",
            },
            "output_dir": {
                "type": "string",
                "description": "输出目录（工作区内相对路径），默认自动创建",
            },
            "api_base_url": {
                "type": "string",
                "description": "LLM API 地址，默认使用 agent 配置",
            },
            "api_key": {
                "type": "string",
                "description": "LLM API Key，默认使用 agent 配置",
            },
            "model": {
                "type": "string",
                "description": "模型名称，默认使用 agent 配置（需要支持多模态视觉输入的模型，如 qwen-vl-plus）",
            },
        },
        "required": ["command", "pdf_path"],
    }

    def __init__(self, workspace_dir: Path, api_key: str = "", base_url: str = "", model: str = "") -> None:
        super().__init__(workspace_dir)
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._output_base = workspace_dir / "generated_documents"
        self._output_base.mkdir(parents=True, exist_ok=True)
        # 如果没有提供 model，用 qwen-vl-plus（支持视觉的模型）
        if not self._model:
            self._model = "qwen-vl-plus"

    def set_api_config(self, api_key: str, base_url: str, model: str = "") -> None:
        """动态设置 API 配置（从 agent 传入）。"""
        if api_key:
            self._api_key = api_key
        if base_url:
            self._base_url = base_url.rstrip("/")
        if model:
            self._model = model

    def run(self, arguments: dict[str, Any], progress_callback: Callable[[str], None] | None = None) -> ToolResult:
        command = str(arguments.get("command", "")).strip().lower()
        pdf_path_str = str(arguments.get("pdf_path", "")).strip()
        page_range = str(arguments.get("page_range", "")).strip()
        instruction = str(arguments.get("instruction", "")).strip()
        output_dir_str = str(arguments.get("output_dir", "")).strip()

        # API 配置（参数覆盖 > 初始化值）
        api_key = str(arguments.get("api_key", self._api_key)).strip()
        base_url = str(arguments.get("api_base_url", self._base_url)).strip()
        model = str(arguments.get("model", self._model)).strip()

        if not pdf_path_str:
            return ToolResult(False, "请提供 pdf_path")

        # 解析 PDF 路径
        pdf_path = Path(pdf_path_str)
        if not pdf_path.is_absolute():
            pdf_path = self.workspace_dir / pdf_path_str
        if not pdf_path.exists():
            return ToolResult(False, f"PDF 文件不存在：{pdf_path}")

        if not fitz:
            return ToolResult(False, "需要 PyMuPDF 库：pip install PyMuPDF")

        if command == "info":
            return self._get_pdf_info(pdf_path)

        if command != "read":
            return ToolResult(False, f"不支持的 command：{command}，可选：read / info")

        # 解析输出目录
        output_dir = self._output_base
        if output_dir_str:
            candidate = Path(output_dir_str)
            if not candidate.is_absolute():
                candidate = self.workspace_dir / candidate
            output_dir = candidate
        output_dir.mkdir(parents=True, exist_ok=True)

        # 解析页码范围（支持中文章节描述 → 自动定位）
        page_numbers = self._resolve_page_range(page_range, pdf_path, api_key, base_url, model)
        if not page_numbers:
            return ToolResult(False, "页码范围无效或 PDF 为空")

        # 检查 API 配置
        if not api_key or not base_url:
            return ToolResult(False, "需要配置 API Key 和 Base URL（通过参数传入或在构造时设置）")

        # 第一步：提取页面内容（图片 + 文字）
        pages_data = self._extract_pages(pdf_path, page_numbers)
        if not pages_data:
            return ToolResult(False, "无法提取 PDF 页面内容")

        # 第二步：调用 LLM 视觉 API 识别内容 + 自动推理处理方式
        result = self._process_with_llm(pages_data, instruction, api_key, base_url, model, output_dir)

        return result

    def _get_pdf_info(self, pdf_path: Path) -> ToolResult:
        """获取 PDF 基本信息。"""
        doc = fitz.open(str(pdf_path))
        try:
            total_pages = len(doc)
            # 尝试提取元数据
            meta = doc.metadata
            title = meta.get("title", "") or pdf_path.stem
            author = meta.get("author", "") or "未知"
            file_size = pdf_path.stat().st_size

            # 检测是否为扫描版（尝试提取文字，如果无文字则为扫描版）
            text_sample = ""
            for i in range(min(5, total_pages)):
                t = doc[i].get_text().strip()
                if t:
                    text_sample += t[:200] + "\n"

            is_scanned = len(text_sample) < 50

            info_lines = [
                f"📄 PDF 信息：{pdf_path.name}",
                f"页数：{total_pages}",
                f"标题：{title}",
                f"作者：{author}",
                f"大小：{file_size / 1024:.1f} KB",
                f"类型：{'扫描版（图片）' if is_scanned else '文字版'}",
            ]
            if text_sample:
                info_lines.append(f"\n文字预览：\n{text_sample[:500]}")

            return ToolResult(True, "\n".join(info_lines), {
                "total_pages": total_pages,
                "title": title,
                "author": author,
                "file_size": file_size,
                "is_scanned": is_scanned,
                "text_preview": text_sample[:500] if text_sample else "",
            })
        finally:
            doc.close()

    def _resolve_page_range(
        self, page_range: str, pdf_path: Path,
        api_key: str = "", base_url: str = "", model: str = "",
    ) -> list[int]:
        """智能解析页码范围：支持数字范围或中文章节描述。

        例如 "第三章第一节"、"3-5"、"180-189"、"第3章" 等。
        对中文章节描述，会用视觉 API 扫描 PDF 定位。
        """
        doc = fitz.open(str(pdf_path))
        total = len(doc)
        doc.close()

        if not page_range:
            return list(range(0, min(10, total)))

        # 尝试先按数字范围解析
        numeric_pages = self._parse_page_range(page_range, pdf_path)
        if numeric_pages:
            return numeric_pages

        # 尝试匹配中文章节模式：如 "第三章"、"第三章第一节"、"第3章"、"第3章第1节"
        ch_pattern = r"第([一二三四五六七八九十]+|[0-9]+)章\s*[第节]?\s*([一二三四五六七八九十]+|[0-9]+)?\s*[节]?"
        ch_match = re.search(ch_pattern, page_range)
        if not ch_match:
            # 不认识的格式，返回前10页
            return list(range(0, min(10, total)))

        ch_num_str = ch_match.group(1)
        # 中文数字转阿拉伯数字
        ch_num = self._chinese_to_arabic(ch_num_str)
        sec_num = None
        if ch_match.lastindex >= 2 and ch_match.group(2):
            sec_num = self._chinese_to_arabic(ch_match.group(2))

        # 尝试缓存
        cache_key = f"{pdf_path}:chapter_{ch_num}"
        if cache_key in _chapter_cache:
            info = _chapter_cache[cache_key]
            if sec_num:
                return self._section_pages(info, sec_num)
            return self._chapter_pages(info)

        # 需要视觉 API 定位章节 → 使用二分查找策略
        if not api_key or not base_url:
            return list(range(0, min(10, total)))

        info = self._locate_chapter_with_vision(pdf_path, ch_num, api_key, base_url, model)
        if info:
            _chapter_cache[cache_key] = info
            if sec_num:
                return self._section_pages(info, sec_num)
            return self._chapter_pages(info)

        return list(range(0, min(10, total)))

    def _chinese_to_arabic(self, s: str) -> int:
        """中文数字 → 阿拉伯数字。"""
        mapping = {
            "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
            "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
            "零": 0,
        }
        if s.isdigit():
            return int(s)
        # 简单处理 "十二" = 12, "三" = 3
        if s in mapping:
            return mapping[s]
        if len(s) == 2 and s[0] == "十":
            return 10 + mapping.get(s[1], 0)
        if len(s) == 1 and s[0] == "十":
            return 10
        # 默认识别
        for k, v in mapping.items():
            s = s.replace(k, str(v))
        try:
            return int(s)
        except ValueError:
            return 3  # 默认第三章

    def _locate_chapter_with_vision(
        self, pdf_path: Path, chapter_num: int,
        api_key: str, base_url: str, model: str,
    ) -> dict | None:
        """用视觉 API 在扫描版 PDF 中定位章节起始页。

        返回 {chapter_page, total_pages, offset} 或 None
        """
        ch_names = ["", "一", "二", "三", "四", "五", "六", "七", "八", "九", "十"]
        ch_label = ch_names[chapter_num] if chapter_num < len(ch_names) else str(chapter_num)

        # 策略：先采样扫描首尾几页，估算PDF偏移
        doc = fitz.open(str(pdf_path))
        total = len(doc)
        doc.close()

        if total < 20:
            return None

        # 检查前15页找目录/章节标题模式，缩小范围
        candidate_start = max(0, (chapter_num - 1) * (total // 8) - 20)
        candidate_end = min(total, (chapter_num + 1) * (total // 8) + 20)

        # 用视觉 API 查这40页中的5个采样点
        sample_points = sorted(set([
            candidate_start,
            candidate_start + (candidate_end - candidate_start) // 4,
            candidate_start + (candidate_end - candidate_start) // 2,
            candidate_start + 3 * (candidate_end - candidate_start) // 4,
            candidate_end - 1,
        ]))

        # 读取采样页
        doc = fitz.open(str(pdf_path))
        samples = []
        for idx in sample_points:
            if 0 <= idx < total:
                page = doc[idx]
                matrix = fitz.Matrix(2.0, 2.0)
                pix = page.get_pixmap(matrix=matrix)
                b64 = base64.b64encode(pix.tobytes("png")).decode("utf-8")
                samples.append({"idx": idx, "page_num": idx + 1, "image": b64})
        doc.close()

        # 调用 LLM 识别章节
        endpoint = f"{base_url.rstrip('/')}/chat/completions"
        system_msg = (
            "You are reading a Chinese textbook PDF (scanned, no text layer). "
            "Each page image shows a page with a chapter/section header and a page number at bottom. "
            "Your job: identify the EXACT printed page number where Chapter X starts."
        )
        user_content: list[dict] = [
            {"type": "text", "text": (
                f"I need to find where Chapter {chapter_num} (第{ch_label}章) starts in this PDF. "
                "I'll show you sample pages from different parts. "
                "Based on these samples, tell me the APPROXIMATE printed page number where this chapter starts. "
                "Also tell me the approximate offset: what PDF file page index corresponds to printed page 1?"
                "Return JSON: {\"chapter_page\": number, \"offset\": number, \"total_pages\": number}"
            )}
        ]
        for s in samples:
            user_content.append({"type": "text", "text": f"--- Sample at PDF page {s['page_num']} ---"})
            user_content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{s['image']}"}})

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_content},
            ],
            "temperature": 0.1,
            "max_tokens": 200,
        }

        try:
            resp_text = self._call_api(endpoint, api_key, payload)
            result = json.loads(resp_text)
            chapter_page = result.get("chapter_page", 0)
            offset = result.get("offset", 0)
            tp = result.get("total_pages", total)
            # 计算PDF索引
            pdf_idx = chapter_page + offset - 1 if offset > 0 else chapter_page - 1
            # 如果 offset 不可靠，直接根据采样估算
            start = max(0, pdf_idx - 5)
            end = min(total, pdf_idx + 15)
            return {"chapter_page": chapter_page, "pdf_start": start, "pdf_end": end, "offset": offset}
        except Exception:
            return None

    def _chapter_pages(self, info: dict) -> list[int]:
        """返回整章的页码范围。"""
        start = info.get("pdf_start", 0)
        end = info.get("pdf_end", 20)
        return list(range(start, end))

    def _section_pages(self, info: dict, section_num: int) -> list[int]:
        """返回某节的范围（默认取章的前10页作为第一节）。"""
        start = info.get("pdf_start", 0)
        # 第一节取章首页+后面约10页
        return list(range(start, min(start + 12, info.get("pdf_end", start + 20))))

    def _parse_page_range(self, page_range: str, pdf_path: Path) -> list[int]:
        """解析数字页码范围。"""
        doc = fitz.open(str(pdf_path))
        total = len(doc)
        doc.close()

        if not page_range:
            return []

        pages: list[int] = []
        # 支持 "3"、"3-5"、"1,3,5"、"3-5,7,9-11" 等格式
        parts = re.split(r"[,，]", page_range)
        for part in parts:
            part = part.strip()
            range_match = re.match(r"^(\d+)\s*[-—]\s*(\d+)$", part)
            if range_match:
                start = max(0, int(range_match.group(1)) - 1)
                end = min(total, int(range_match.group(2)))
                pages.extend(range(start, end))
            elif part.isdigit():
                idx = int(part) - 1
                if 0 <= idx < total:
                    pages.append(idx)
        return sorted(set(pages)) if pages else []

    def _extract_pages(self, pdf_path: Path, page_numbers: list[int]) -> list[dict[str, Any]]:
        """提取指定页面的图片和文字。

        返回 [{page_num, image_base64, text, width, height}, ...]
        """
        doc = fitz.open(str(pdf_path))
        pages_data = []
        try:
            for page_idx in page_numbers:
                if page_idx >= len(doc):
                    continue
                page = doc[page_idx]
                # 尝试提取文字
                text = page.get_text().strip()

                # 渲染为图片（3x 分辨率用于 OCR / 视觉识别）
                matrix = fitz.Matrix(2.0, 2.0)  # 2x 缩放平衡质量和大小
                pix = page.get_pixmap(matrix=matrix)
                img_bytes = pix.tobytes("png")
                img_b64 = base64.b64encode(img_bytes).decode("utf-8")

                pages_data.append({
                    "page_num": page_idx + 1,
                    "text": text,
                    "image_base64": img_b64,
                    "image_size": len(img_bytes),
                    "width": pix.width,
                    "height": pix.height,
                })
        finally:
            doc.close()

        return pages_data

    def _process_with_llm(
        self,
        pages_data: list[dict[str, Any]],
        instruction: str,
        api_key: str,
        base_url: str,
        model: str,
        output_dir: Path,
    ) -> ToolResult:
        """调用 LLM 视觉 API 识别内容并自动推理处理方式。"""
        # 构造消息
        system_prompt = self._build_system_prompt(instruction)
        messages = self._build_messages(system_prompt, pages_data, instruction)

        # 调用 API
        endpoint = f"{base_url.rstrip('/')}/chat/completions"

        # 构建请求体
        payload = {
            "model": model,
            "messages": messages,
            "temperature": 0.3,
            "max_tokens": 4096,
        }

        try:
            response_text = self._call_api(endpoint, api_key, payload)
        except Exception as e:
            return ToolResult(False, f"LLM 调用失败：{e}")

        # 解析 LLM 返回的 JSON
        try:
            result = json.loads(response_text)
        except json.JSONDecodeError:
            # 如果不是 JSON，当作文本内容处理
            result = {
                "action": "write_note",
                "title": f"PDF阅读笔记_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                "content": response_text,
                "format": "md",
            }

        action = result.get("action", "write_note")
        title = result.get("title", f"PDF笔记_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        content = result.get("content", response_text if "content" not in result else "")
        fmt = result.get("format", "md")
        filename = result.get("filename", "")
        extra = result.get("extra", {})

        # 根据 action 执行不同操作
        if action == "write_note":
            return self._action_write_note(content, title, filename, fmt, output_dir, extra)
        elif action == "generate_pdf":
            return self._action_generate_pdf(content, title, filename, output_dir, extra)
        elif action == "generate_ppt":
            return self._action_generate_ppt(content, title, filename, output_dir, extra)
        elif action == "generate_questions":
            return self._action_write_note(content, title, filename, fmt, output_dir, extra)
        elif action == "generate_mindmap":
            return self._action_write_note(content, title, filename, "mm.md", output_dir, extra)
        else:
            # 默认写入 md
            return self._action_write_note(content, title, filename, fmt, output_dir, extra)

    def _build_system_prompt(self, instruction: str) -> str:
        base = """你是一个 PDF 智能阅读助手。用户可以传入 PDF 页面的图片（扫描版）或文字内容。

你的任务：
1. **识别页面内容**：读取图片中的文字、公式、图表等信息
2. **自动推理**：根据内容自主决定最合适的处理方式，输出 JSON

请以 JSON 格式返回，必须包含以下字段：
```json
{
  "action": "操作类型",
  "title": "标题",
  "content": "生成的内容",
  "format": "输出格式",
  "filename": "文件名（不含扩展名）",
  "extra": {}
}
```

**action 的可选值**：
- `"write_note"`: 写笔记/总结（最常用）→ 生成 .md 文件
- `"generate_pdf"`: 生成结构化的 PDF 文档
- `"generate_ppt"`: 生成 PPT 幻灯片
- `"generate_questions"`: 生成习题/考题
- `"generate_mindmap"`: 生成思维导图（Markdown 大纲格式）

**format 的可选值**：
- `"md"`: Markdown（用于笔记、总结、大纲）
- `"txt"`: 纯文本
- `"pdf"`/`"ppt"`: 用于对应 action

**推理规则**：
- 如果内容是"第三章 向量组与线性方程组"等教材内容，优先总结为结构化笔记（action=write_note）
- 如果内容有明显的问题/习题，同时生成考题（content 中同时包含笔记+考题）
- 如果内容适合展示，考虑 generate_ppt
- 如果内容信息量大、结构清晰，考虑 generate_pdf
- content 要完整、详细、有条理

"""
        if instruction:
            base += f"\n额外的用户指令：{instruction}\n请结合指令调整处理方式。"

        base += """
当前日期：{date}

请严格返回 JSON 格式，不要包含其他文字。
""".format(date=datetime.now().strftime("%Y年%m月%d日"))

        return base

    def _build_messages(
        self, system_prompt: str, pages_data: list[dict[str, Any]], instruction: str
    ) -> list[dict[str, Any]]:
        """构建消息列表，支持多模态视觉输入。"""
        messages = [{"role": "system", "content": system_prompt}]

        # 构建用户消息内容
        user_content: list[dict[str, Any]] = []

        # 添加文字说明
        text_summary = f"以下是 PDF 中 {len(pages_data)} 页的内容，请识别并处理：\n\n"
        for p in pages_data:
            text_summary += f"--- 第{p['page_num']}页 ---\n"
            if p["text"]:
                text_summary += f"[文字层]: {p['text'][:1000]}\n"
            text_summary += f"[页面尺寸: {p['width']}x{p['height']}]\n\n"

        # 对于文字版 PDF，直接传文字即可
        has_text = any(p["text"] for p in pages_data)
        if has_text and all(len(p.get("text", "")) > 50 for p in pages_data if p.get("text")):
            # 文字充足，不用图片
            user_content.append({"type": "text", "text": text_summary})
        else:
            # 扫描版 PDF：传缩略图 + 文字说明
            # 先传说明
            user_content.append({
                "type": "text",
                "text": f"以下是 PDF 中 {len(pages_data)} 页的扫描图片，请识别每页内容并处理。\n"
                        f"总共 {len(pages_data)} 页。\n"
                        + (f"额外指令：{instruction}\n" if instruction else ""),
            })
            # 每页传一张图（控制大小，最多传 10 页避免 token 超限）
            for p in pages_data[:10]:
                user_content.append({
                    "type": "text",
                    "text": f"=== 第{p['page_num']}页 ===",
                })
                user_content.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{p['image_base64']}",
                    },
                })

        messages.append({"role": "user", "content": user_content})
        return messages

    def _call_api(self, endpoint: str, api_key: str, payload: dict[str, Any]) -> str:
        """调用 OpenAI 兼容 API。"""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(endpoint, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"API HTTP {e.code}: {err_body[:500]}") from e
        except Exception as e:
            raise RuntimeError(f"API 请求失败：{e}") from e

        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as e:
            raise RuntimeError(f"API 返回格式异常：{json.dumps(body, ensure_ascii=False)[:500]}") from e

        # 尝试提取 JSON（可能被 markdown 包裹）
        return self._extract_json(content)

    def _extract_json(self, text: str) -> str:
        """从 LLM 返回中提取 JSON 部分。"""
        # 尝试解析 JSON 代码块
        json_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if json_match:
            return json_match.group(1).strip()

        # 尝试直接解析
        text = text.strip()
        if text.startswith("{"):
            return text

        # 如果都不是，作为纯文本返回
        return json.dumps({
            "action": "write_note",
            "title": "PDF阅读笔记",
            "content": text,
            "format": "md",
        })

    # ── Action 执行 ──────────────────────────

    def _action_write_note(
        self,
        content: str,
        title: str,
        filename: str,
        fmt: str,
        output_dir: Path,
        extra: dict[str, Any],
    ) -> ToolResult:
        """写笔记/总结到文件。"""
        if not filename:
            safe_title = re.sub(r"[\\/:*?\"<>|]+", "_", title)[:40]
            filename = f"{safe_title}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        ext_map = {
            "md": ".md",
            "txt": ".txt",
            "mm": ".md",
            "json": ".json",
        }
        ext = ext_map.get(fmt, ".md")
        file_path = output_dir / f"{filename}{ext}"

        file_path.write_text(content, encoding="utf-8")
        word_count = len(content.replace("\n", ""))

        return ToolResult(
            True,
            f"✅ 笔记已生成！\n文件：{file_path}\n字数：{word_count}\n标题：{title}",
            {
                "action": "write_note",
                "file_path": str(file_path),
                "word_count": word_count,
                "title": title,
            },
        )

    def _action_generate_pdf(
        self,
        content: str,
        title: str,
        filename: str,
        output_dir: Path,
        extra: dict[str, Any],
    ) -> ToolResult:
        """生成 PDF 文档（委托给 pdf_gen_tool）。"""
        try:
            from clawmini.tools.pdf_gen_tool import DocumentGenerationTool

            gen = DocumentGenerationTool(workspace_dir=self.workspace_dir)
            result = gen.run({
                "command": "create",
                "format": "pdf",
                "content": content,
                "title": title,
                "filename": filename or f"pdf_from_reading_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                "output_dir": str(output_dir.relative_to(self.workspace_dir))
                if output_dir != self._output_base
                else "",
            })
            return result
        except Exception as e:
            # 回退到写 md
            return self._action_write_note(
                content, title, filename, "md", output_dir, extra
            )

    def _action_generate_ppt(
        self,
        content: str,
        title: str,
        filename: str,
        output_dir: Path,
        extra: dict[str, Any],
    ) -> ToolResult:
        """生成 PPT（委托给 pdf_gen_tool）。"""
        try:
            from clawmini.tools.pdf_gen_tool import DocumentGenerationTool

            gen = DocumentGenerationTool(workspace_dir=self.workspace_dir)
            result = gen.run({
                "command": "create",
                "format": "ppt",
                "content": content,
                "title": title,
                "filename": filename or f"ppt_from_reading_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                "output_dir": str(output_dir.relative_to(self.workspace_dir))
                if output_dir != self._output_base
                else "",
            })
            return result
        except Exception as e:
            return self._action_write_note(
                content, title, filename, "md", output_dir, extra
            )
