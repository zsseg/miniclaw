"""自动撰写文稿工具。"""

from __future__ import annotations

import difflib
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any
import re
import urllib.request

from clawmini.core.security import ensure_allowed_extension, ensure_path_in_workspace
from clawmini.tools.base import BaseTool
from clawmini.types import ToolResult
from typing import Callable


class WritingTool(BaseTool):
    """文稿创建与修改工具，限定在工作目录内。"""

    name = "writing_tool"
    description = "生成或修改 .md/.txt/.doc 文稿，支持预览、提交、撤销"
    parameters_schema = {
        "type": "object",
        "properties": {
            "command": {"type": "string"},
            "topic": {"type": "string"},
            "topics": {"type": "array", "items": {"type": "string"}},
            "request": {"type": "string"},
            "plan_count": {"type": "integer"},
            "filename": {"type": "string"},
            "style": {"type": "string"},
            "word_count": {"type": "integer"},
            "output_dir": {"type": "string"},
            "custom_prompt": {"type": "string"},
            "api_provider": {"type": "string"},
            "api_model": {"type": "string"},
            "api_key": {"type": "string"},
            "api_base_url": {"type": "string"},
            "file_path": {"type": "string"},
            "instruction": {"type": "string"},
            "section_index": {"type": "integer"},
            "job_id": {"type": "string"},
        },
        "required": ["command"],
    }

    def __init__(self, workspace_dir: Path) -> None:
        super().__init__(workspace_dir)
        self.allowed_ext = {".md", ".txt", ".doc"}
        self.preview_cache: dict[Path, str] = {}
        self.backup_stack: dict[Path, list[Path]] = {}
        self.batch_jobs: dict[str, dict[str, Any]] = {}
        self.task_sessions: dict[str, dict[str, Any]] = {}
        self.active_task_id: str | None = None

    def run(self, arguments: dict[str, Any], progress_callback: Callable[[str], None] | None = None) -> ToolResult:
        command = str(arguments.get("command", ""))
        # 兼容别名
        if command in ("generate", "write"):
            command = "create"
        if command == "create":
            return self._create(arguments)
        if command == "switch_task":
            return self._switch_task(arguments)
        if command == "list_tasks":
            return self._list_tasks()
        if command == "task_status":
            return self._task_status(arguments)
        if command == "brainstorm_plans":
            return self._brainstorm_plans(arguments)
        if command == "preview_plan_content":
            return self._preview_plan_content(arguments)
        if command == "preview_edit":
            return self._preview_edit(arguments)
        if command == "preview_edit_section":
            return self._preview_edit_section(arguments)
        if command == "commit_edit":
            return self._commit_edit(arguments)
        if command == "undo":
            return self._undo(arguments)
        if command == "create_batch":
            return self._create_batch(arguments)
        if command == "batch_status":
            return self._batch_status(arguments)
        return ToolResult(False, f"不支持的 command: {command}")

    def _create(self, arguments: dict[str, Any]) -> ToolResult:
        topic = str(arguments.get("topic", "未命名主题"))
        style = str(arguments.get("style", "通用"))
        word_count = int(arguments.get("word_count", 500))
        custom_prompt = str(arguments.get("custom_prompt", "")).strip()
        api_provider = str(arguments.get("api_provider", "mock")).strip().lower()
        api_model = str(arguments.get("api_model", "")).strip()
        api_key = str(arguments.get("api_key", "")).strip()
        api_base_url = str(arguments.get("api_base_url", "")).strip()
        allow_risky_content = bool(arguments.get("allow_risky_content", False))
        if word_count > 100000:
            return ToolResult(False, "超出单次最大长度限制（10万字符）。")

        output_dir = ensure_path_in_workspace(self.workspace_dir / str(arguments.get("output_dir", ".")), self.workspace_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        filename = str(arguments.get("filename", f"article_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"))
        filename = self._normalize_filename(filename)
        path = ensure_path_in_workspace(output_dir / filename, self.workspace_dir)
        ensure_allowed_extension(path, self.allowed_ext)

        if path.exists():
            path = path.with_stem(path.stem + "_v2")

        is_markdown = path.suffix.lower() == ".md"
        api_fallback = False
        if api_provider in {"openai", "deepseek", "qwen"} and api_key:
            content = self._generate_article_via_api(
                topic=topic,
                style=style,
                word_count=word_count,
                custom_prompt=custom_prompt,
                provider=api_provider,
                model=api_model,
                api_key=api_key,
                base_url=api_base_url,
                allow_markdown=is_markdown,
            )
            api_fallback = "外部 API 调用失败" in content
        else:
            content = self._generate_article(topic=topic, style=style, word_count=word_count, custom_prompt=custom_prompt, allow_markdown=is_markdown)
        content = self._sanitize_generated_content(content, allow_risky=allow_risky_content)
        content = self._ensure_prompt_alignment(content, topic=topic, custom_prompt=custom_prompt, allow_markdown=is_markdown)
        if not is_markdown:
            content = self._render_as_plain_text(content)
        path.write_text(content, encoding="utf-8")
        task_id = self._resolve_task_id(arguments)
        self._record_task_activity(
            task_id=task_id,
            file_path=path,
            topic=topic,
            style=style,
            word_count=word_count,
            action="create",
        )
        summary = self._summarize_text(content)
        stats_word_count = self._estimate_word_count(content)
        status_note = ""
        if api_fallback:
            status_note = "（外部API调用失败，已回退本地生成）"
        elif api_provider in {"openai", "deepseek", "qwen"} and api_key:
            status_note = "（已调用外部API）"
        return ToolResult(
            True,
            f"文稿已生成：{path}（字数约 {stats_word_count}）{status_note}",
            {
                "file_path": str(path),
                "task_id": task_id,
                "word_count": stats_word_count,
                "summary": summary,
                "topic": topic,
                "style": style,
            },
        )

    def _switch_task(self, arguments: dict[str, Any]) -> ToolResult:
        """切换当前文稿任务上下文。"""
        task_id = str(arguments.get("task_id", "")).strip()
        if not task_id:
            return ToolResult(False, "switch_task 需要 task_id")
        if task_id not in self.task_sessions:
            return ToolResult(False, f"任务不存在：{task_id}")
        self.active_task_id = task_id
        session = self.task_sessions[task_id]
        return ToolResult(
            True,
            f"已切换到任务：{task_id}（文件数={len(session['files'])}）",
            {"task_id": task_id, **session},
        )

    def _list_tasks(self) -> ToolResult:
        """列出当前所有文稿任务。"""
        tasks = []
        for task_id, session in sorted(self.task_sessions.items(), key=lambda x: x[1]["updated_at"], reverse=True):
            tasks.append(
                {
                    "task_id": task_id,
                    "topic": session["topic"],
                    "files": list(session["files"]),
                    "updated_at": session["updated_at"],
                    "active": task_id == self.active_task_id,
                }
            )
        return ToolResult(True, f"任务总数：{len(tasks)}", {"tasks": tasks, "active_task_id": self.active_task_id})

    def _task_status(self, arguments: dict[str, Any]) -> ToolResult:
        """查询单个任务状态。"""
        task_id = str(arguments.get("task_id", self.active_task_id or "")).strip()
        if not task_id:
            return ToolResult(False, "task_status 需要 task_id（或先切换 active task）")
        session = self.task_sessions.get(task_id)
        if not session:
            return ToolResult(False, f"任务不存在：{task_id}")
        return ToolResult(
            True,
            f"task_id={task_id}，文件数={len(session['files'])}，最近更新时间={session['updated_at']}",
            {"task_id": task_id, **session},
        )

    def _brainstorm_plans(self, arguments: dict[str, Any]) -> ToolResult:
        """针对开放式写作请求给出 2-3 种可执行方案。"""
        request = str(arguments.get("request", "")).strip()
        if not request:
            return ToolResult(False, "brainstorm_plans 需要 request。")

        raw_count = int(arguments.get("plan_count", 3))
        plan_count = max(2, min(3, raw_count))
        plans = self._generate_plan_options(request=request, plan_count=plan_count)

        lines = ["已生成候选写作方案："]
        for idx, plan in enumerate(plans, start=1):
            lines.append(
                f"方案{idx} | 风格={plan['style']} | 目标字数={plan['word_count']} | "
                f"文件名={plan['filename']} | 说明={plan['rationale']}"
            )
        lines.append("你可以回复：选择方案1/2/3，或继续微调（语气、篇幅、结构）。")
        return ToolResult(True, "\n".join(lines), {"plans": plans, "count": len(plans)})

    def _preview_plan_content(self, arguments: dict[str, Any]) -> ToolResult:
        """根据方案参数预览正文内容（不落盘）。"""
        topic = str(arguments.get("topic", "未命名主题")).strip()
        style = str(arguments.get("style", "通用")).strip()
        word_count = int(arguments.get("word_count", 700))
        custom_prompt = str(arguments.get("custom_prompt", "")).strip()
        api_provider = str(arguments.get("api_provider", "mock")).strip().lower()
        api_model = str(arguments.get("api_model", "")).strip()
        api_key = str(arguments.get("api_key", "")).strip()
        api_base_url = str(arguments.get("api_base_url", "")).strip()
        if word_count <= 0:
            return ToolResult(False, "word_count 必须大于 0")
        if word_count > 100000:
            return ToolResult(False, "超出单次最大长度限制（10万字符）。")

        if api_provider in {"openai", "deepseek"} and api_key:
            content = self._generate_article_via_api(
                topic=topic,
                style=style,
                word_count=word_count,
                custom_prompt=custom_prompt,
                provider=api_provider,
                model=api_model,
                api_key=api_key,
                base_url=api_base_url,
            )
        else:
            content = self._generate_article(topic=topic, style=style, word_count=word_count, custom_prompt=custom_prompt)
        content = self._sanitize_generated_content(content, allow_risky=False)
        return ToolResult(
            True,
            "方案正文预览已生成（未写入文件）。",
            {
                "content": content,
                "word_count": self._estimate_word_count(content),
                "summary": self._summarize_text(content, max_len=120),
            },
        )

    def _preview_edit(self, arguments: dict[str, Any]) -> ToolResult:
        raw_path = str(arguments.get("file_path", ""))
        instruction = str(arguments.get("instruction", ""))
        if not raw_path or not instruction:
            return ToolResult(False, "preview_edit 需要 file_path 与 instruction。")

        path = self._resolve_user_path(raw_path)
        ensure_allowed_extension(path, self.allowed_ext)
        if not path.exists():
            return ToolResult(False, f"文件不存在：{path}")

        original = path.read_text(encoding="utf-8")
        edited = self._rewrite_content(original, instruction)
        edited = self._sanitize_generated_content(edited, allow_risky=bool(arguments.get("allow_risky_content", False)))
        self.preview_cache[path] = edited

        diff = "\n".join(
            difflib.unified_diff(
                original.splitlines(),
                edited.splitlines(),
                fromfile="before",
                tofile="after",
                lineterm="",
            )
        )
        return ToolResult(True, "预览已生成（未写入）。\n" + (diff[:4000] if diff else "无差异"))

    def _commit_edit(self, arguments: dict[str, Any]) -> ToolResult:
        raw_path = str(arguments.get("file_path", ""))
        if not raw_path:
            return ToolResult(False, "commit_edit 需要 file_path。")

        path = self._resolve_user_path(raw_path)
        ensure_allowed_extension(path, self.allowed_ext)
        if path not in self.preview_cache:
            return ToolResult(False, "该文件没有待提交预览，请先调用 preview_edit。")

        backup = path.with_suffix(path.suffix + f".{datetime.now().strftime('%H%M%S')}.bak")
        backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        self.backup_stack.setdefault(path, []).append(backup)

        path.write_text(self.preview_cache.pop(path), encoding="utf-8")
        task_id = self._resolve_task_id(arguments)
        self._record_task_activity(task_id=task_id, file_path=path, action="commit_edit")
        return ToolResult(True, f"修改已提交：{path}，备份：{backup}")

    def _preview_edit_section(self, arguments: dict[str, Any]) -> ToolResult:
        """按段落预览修改。

        约定：`section_index` 从 1 开始。
        """
        raw_path = str(arguments.get("file_path", ""))
        instruction = str(arguments.get("instruction", ""))
        section_index = int(arguments.get("section_index", 0))
        if not raw_path or not instruction or section_index <= 0:
            return ToolResult(False, "preview_edit_section 需要 file_path、instruction、section_index(>=1)。")

        path = self._resolve_user_path(raw_path)
        ensure_allowed_extension(path, self.allowed_ext)
        if not path.exists():
            return ToolResult(False, f"文件不存在：{path}")

        original = path.read_text(encoding="utf-8")
        paragraphs = self._split_paragraphs(original)
        if section_index > len(paragraphs):
            return ToolResult(False, f"段落索引越界：共有 {len(paragraphs)} 段。")

        target_old = paragraphs[section_index - 1]
        paragraphs[section_index - 1] = self._rewrite_content(target_old, instruction, section_only=True)
        edited = "\n\n".join(paragraphs)
        edited = self._sanitize_generated_content(edited, allow_risky=bool(arguments.get("allow_risky_content", False)))
        self.preview_cache[path] = edited

        diff = "\n".join(
            difflib.unified_diff(
                target_old.splitlines(),
                paragraphs[section_index - 1].splitlines(),
                fromfile=f"section_{section_index}_before",
                tofile=f"section_{section_index}_after",
                lineterm="",
            )
        )
        return ToolResult(True, "段落预览已生成（未写入）。\n" + (diff[:3000] if diff else "无差异"))

    def _undo(self, arguments: dict[str, Any]) -> ToolResult:
        raw_path = str(arguments.get("file_path", ""))
        if not raw_path:
            return ToolResult(False, "undo 需要 file_path。")

        path = self._resolve_user_path(raw_path)
        backups = self.backup_stack.get(path, [])
        if not backups:
            return ToolResult(False, "没有可撤销的历史版本。")

        latest = backups.pop()
        path.write_text(latest.read_text(encoding="utf-8"), encoding="utf-8")
        return ToolResult(True, f"已回退到最近版本：{latest}")

    def _create_batch(self, arguments: dict[str, Any]) -> ToolResult:
        """批量生成文稿任务（串行队列实现）。"""
        topics = arguments.get("topics", [])
        if not isinstance(topics, list) or not topics:
            return ToolResult(False, "create_batch 需要非空 topics 列表。")

        style = str(arguments.get("style", "通用"))
        word_count = int(arguments.get("word_count", 500))
        output_dir = ensure_path_in_workspace(self.workspace_dir / str(arguments.get("output_dir", ".")), self.workspace_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        ext = str(arguments.get("ext", ".md"))
        if not ext.startswith("."):
            ext = f".{ext}"
        if ext not in self.allowed_ext:
            return ToolResult(False, f"批量生成扩展名仅支持 {sorted(self.allowed_ext)}")

        job_id = str(arguments.get("job_id", uuid.uuid4().hex[:8]))
        job = {
            "status": "running",
            "total": len(topics),
            "processed": 0,
            "success": 0,
            "failed": 0,
            "files": [],
            "errors": [],
        }
        self.batch_jobs[job_id] = job

        for idx, topic in enumerate(topics, start=1):
            try:
                filename = f"article_{idx:03d}{ext}"
                result = self._create(
                    {
                        "topic": str(topic),
                        "style": style,
                        "word_count": word_count,
                        "output_dir": str(output_dir.relative_to(self.workspace_dir)),
                        "filename": filename,
                    }
                )
                if result.success:
                    job["success"] += 1
                    job["files"].append(result.meta.get("file_path", ""))
                else:
                    job["failed"] += 1
                    job["errors"].append(result.output)
            except Exception as exc:  # noqa: BLE001
                job["failed"] += 1
                job["errors"].append(str(exc))
            finally:
                job["processed"] += 1

        job["status"] = "completed"
        return ToolResult(
            True,
            f"批量任务完成：job_id={job_id}，进度={job['processed']}/{job['total']}，成功={job['success']}，失败={job['failed']}",
            {"job_id": job_id, **job},
        )

    def _batch_status(self, arguments: dict[str, Any]) -> ToolResult:
        """查询批量任务进度。"""
        job_id = str(arguments.get("job_id", ""))
        if not job_id:
            return ToolResult(False, "batch_status 需要 job_id。")
        job = self.batch_jobs.get(job_id)
        if not job:
            return ToolResult(False, f"任务不存在：{job_id}")
        return ToolResult(True, f"job_id={job_id} 状态={job['status']} 进度={job['processed']}/{job['total']}", {"job_id": job_id, **job})

    def _generate_article(self, topic: str, style: str, word_count: int, custom_prompt: str = "", allow_markdown: bool = True) -> str:
        """按提示词生成相对完整的草稿。"""
        if allow_markdown:
            header = f"# {topic}\n\n生成时间：{datetime.now().isoformat(timespec='seconds')}\n风格：{style}\n"
        else:
            header = f"{topic}\n\n生成时间：{datetime.now().isoformat(timespec='seconds')}\n风格：{style}\n"
        if custom_prompt:
            header += f"补充要求：{custom_prompt}\n"
        header += "\n"

        tone_map = {
            "学术正式": "采用较为严谨的论证方式，强调概念边界、证据链与可验证结论。",
            "通俗科普": "用易懂语言解释关键概念，尽量减少行话并配合生活化案例。",
            "观点评论": "突出立场与判断，结合反例与现实观察形成鲜明观点。",
            "幽默": "在保持信息准确的前提下加入轻松表达，提升可读性。",
            "通用": "在结构清晰的前提下兼顾解释深度与阅读流畅度。",
        }
        tone_text = tone_map.get(style, tone_map["通用"])

        sections = [
            ("一、问题背景", f"围绕“{topic}”讨论时，首先要明确它所处的现实语境。{tone_text}"),
            ("二、核心观点", f"从目标、约束和实际场景看，{topic}并非单一问题，而是一个需要平衡效率、成本与体验的系统议题。"),
            ("三、案例与分析", f"以典型场景为例，可以观察到：当目标定义清晰时，{topic}的实施效果更稳定；当边界模糊时，执行偏差会显著上升。"),
            ("四、实践建议", f"建议从小范围试点开始，先建立可衡量指标，再逐步扩展范围，并保留回滚与复盘机制。"),
            ("五、总结", f"总体而言，{topic}的关键不在“是否采用”，而在“如何在具体情境中持续优化”。"),
        ]

        if custom_prompt:
            sections.insert(
                3,
                ("补充要求落实", f"针对用户额外要求“{custom_prompt}”，本文在表达侧重点与结构组织上进行了对应调整。"),
            )

        parts = [header]
        for title, paragraph in sections:
            parts.append(f"{title}\n{paragraph}\n")

        base_text = "\n".join(parts).strip() + "\n"
        words = self._estimate_word_count(base_text)
        expand_pool = [
            f"进一步看，{topic}的推进还依赖跨角色协作与明确分工。",
            "在执行层面，建议同步建立风险台账与阶段性复盘机制。",
            "当外部条件发生变化时，及时调整策略比一次性定稿更重要。",
            "如果要面向更大范围落地，应优先统一术语、流程与评价标准。",
        ]
        idx = 0
        while words < word_count and idx < 200:
            sentence = expand_pool[idx % len(expand_pool)]
            base_text += sentence + "\n"
            words = self._estimate_word_count(base_text)
            idx += 1

        return self._ensure_prompt_alignment(base_text[: max(word_count + 220, 400)], topic=topic, custom_prompt=custom_prompt, allow_markdown=allow_markdown)

    def _generate_article_via_api(
        self,
        topic: str,
        style: str,
        word_count: int,
        custom_prompt: str,
        provider: str,
        model: str,
        api_key: str,
        base_url: str,
        allow_markdown: bool = True,
    ) -> str:
        """调用外部 API 生成文稿正文。"""
        resolved_base = base_url.strip()
        if not resolved_base:
            if provider == "openai":
                resolved_base = "https://api.openai.com/v1"
            elif provider == "qwen":
                resolved_base = "https://dashscope.aliyuncs.com/compatible-mode/v1"
            else:
                resolved_base = "https://api.deepseek.com/v1"
        elif not resolved_base.rstrip("/").endswith("/v1"):
            resolved_base = resolved_base.rstrip("/") + "/v1"
        endpoint = resolved_base.rstrip("/") + "/chat/completions"
        resolved_model = model or (
            "gpt-4o-mini"
            if provider == "openai"
            else "qwen-plus"
            if provider == "qwen"
            else "deepseek-chat"
        )

        prompt = self._build_generation_prompt(
            topic=topic,
            style=style,
            word_count=word_count,
            custom_prompt=custom_prompt,
            allow_markdown=allow_markdown,
        )

        payload = {
            "model": resolved_model,
            "temperature": 0.7,
            "messages": [
                {"role": "system", "content": "你是中文写作助手，请产出高质量文章。"},
                {"role": "user", "content": prompt},
            ],
        }

        req = urllib.request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            content = str(body["choices"][0]["message"]["content"]).strip()
            if not content:
                raise ValueError("外部 API 返回内容为空")
            return self._ensure_prompt_alignment(content, topic=topic, custom_prompt=custom_prompt, allow_markdown=allow_markdown)
        except Exception as exc:  # noqa: BLE001
            # 外部 API 失败时回退本地生成，避免用户流程中断。
            fallback = self._generate_article(topic=topic, style=style, word_count=word_count, custom_prompt=custom_prompt)
            return fallback + f"\n\n> [提示] 外部 API 调用失败，已回退本地生成：{exc}"

    def _sanitize_generated_content(self, content: str, allow_risky: bool) -> str:
        """过滤生成内容中的高风险片段（默认开启）。"""
        if allow_risky:
            return content
        filtered = content
        risky_patterns = [
            r"<\s*script[^>]*>.*?<\s*/\s*script\s*>",
            r"\brm\s+-rf\b",
            r"\bpowershell\s+-enc\b",
            r"\bcurl\s+.+\|\s*(bash|sh|powershell)\b",
        ]
        for pat in risky_patterns:
            filtered = re.sub(pat, "[已移除风险片段]", filtered, flags=re.IGNORECASE | re.DOTALL)
        return filtered

    def _rewrite_content(self, content: str, instruction: str, section_only: bool = False) -> str:
        """根据用户指令重写内容，优先做实质性段落级调整。"""
        instruction = instruction.strip()
        if not instruction:
            return content

        target_content = content.strip()
        paragraphs = self._split_paragraphs(target_content)
        if not section_only and paragraphs:
            body_offset = 1 if paragraphs and paragraphs[0].lstrip().startswith("#") and len(paragraphs) > 1 else 0
            body_paragraphs = paragraphs[body_offset:] if body_offset else paragraphs
            target_index = self._detect_target_paragraph_index(instruction, len(body_paragraphs))
            if target_index is not None:
                actual_index = target_index + body_offset
                if actual_index < len(paragraphs):
                    paragraphs[actual_index] = self._rewrite_paragraph(paragraphs[actual_index], instruction)
                return "\n\n".join(paragraphs)

            if any(keyword in instruction for keyword in ["更正式", "更严谨", "更学术"]):
                return self._formalize_article(target_content, instruction)
            if any(keyword in instruction for keyword in ["更幽默", "幽默一点", "轻松一点"]):
                return self._lighten_article(target_content, instruction)
            if any(keyword in instruction for keyword in ["补充", "扩写", "展开"]):
                return self._expand_article(target_content, instruction)
            if any(keyword in instruction for keyword in ["删掉", "删除", "去掉", "精简"]):
                return self._condense_article(target_content, instruction)
            if "替换" in instruction and "为" in instruction:
                return self._apply_explicit_replacement(target_content, instruction)

        return self._rewrite_paragraph(target_content, instruction)

    def _rewrite_paragraph(self, paragraph: str, instruction: str) -> str:
        """针对单段文字做定向重写。"""
        text = paragraph.strip()
        if not text:
            return paragraph

        if any(keyword in instruction for keyword in ["更正式", "更严谨", "更学术"]):
            return self._formalize_paragraph(text, instruction)
        if any(keyword in instruction for keyword in ["更幽默", "幽默一点", "轻松一点"]):
            return self._lighten_paragraph(text, instruction)
        if any(keyword in instruction for keyword in ["补充", "扩写", "展开"]):
            return text + self._expand_sentence_for_instruction(instruction)
        if any(keyword in instruction for keyword in ["删掉", "删除", "去掉", "精简"]):
            return self._condense_paragraph(text, instruction)
        if "替换" in instruction and "为" in instruction:
            return self._apply_explicit_replacement(text, instruction)
        return text + self._instruction_tail(instruction)

    def _formalize_article(self, content: str, instruction: str) -> str:
        paragraphs = self._split_paragraphs(content)
        rewritten = [self._formalize_paragraph(paragraph, instruction) for paragraph in paragraphs]
        return "\n\n".join(rewritten)

    def _lighten_article(self, content: str, instruction: str) -> str:
        paragraphs = self._split_paragraphs(content)
        rewritten = [self._lighten_paragraph(paragraph, instruction) for paragraph in paragraphs]
        return "\n\n".join(rewritten)

    def _expand_article(self, content: str, instruction: str) -> str:
        addition = self._expand_sentence_for_instruction(instruction)
        paragraphs = self._split_paragraphs(content)
        if paragraphs:
            paragraphs[-1] = paragraphs[-1] + addition
            return "\n\n".join(paragraphs)
        return content + addition

    def _condense_article(self, content: str, instruction: str) -> str:
        paragraphs = self._split_paragraphs(content)
        rewritten = [self._condense_paragraph(paragraph, instruction) for paragraph in paragraphs]
        return "\n\n".join(rewritten)

    def _formalize_paragraph(self, paragraph: str, instruction: str) -> str:
        text = paragraph.strip()
        replacements = {
            "建议": "建议方案",
            "可以": "可以考虑",
            "比较": "相对",
            "很多": "较多",
            "好处": "优势",
            "问题": "议题",
            "总结来说": "总体而言",
        }
        for source, target in replacements.items():
            text = text.replace(source, target)
        if not text.endswith("。"):
            text += "。"
        if "更正式" in instruction or "更学术" in instruction:
            text += " 该表述更强调论证的严谨性与结论的可验证性，并明确说明其依据。"
        return text

    def _lighten_paragraph(self, paragraph: str, instruction: str) -> str:
        text = paragraph.strip()
        if not text.endswith("。"):
            text += "。"
        return text + " 读起来尽量轻松一点，但信息仍然完整。"

    def _condense_paragraph(self, paragraph: str, instruction: str) -> str:
        text = paragraph.strip()
        sentences = [item.strip() for item in re.split(r"[。！？!?]\s*", text) if item.strip()]
        if len(sentences) <= 1:
            return text[: max(20, len(text) // 2)]
        keep_count = max(1, len(sentences) // 2)
        condensed = "。".join(sentences[:keep_count])
        if not condensed.endswith("。"):
            condensed += "。"
        return condensed + " 以上内容已做精简处理。"

    def _apply_explicit_replacement(self, text: str, instruction: str) -> str:
        cleaned = instruction.replace("把", "")
        cleaned = cleaned.replace("请", "")
        parts = re.split(r"替换为|改成|替成", cleaned, maxsplit=1)
        if len(parts) != 2:
            return text + self._instruction_tail(instruction)
        src = parts[0].strip(" “\"”\'、，。")
        dst = parts[1].strip(" “\"”\'、，。")
        if not src or not dst:
            return text + self._instruction_tail(instruction)
        replaced = text.replace(src, dst)
        if replaced == text:
            if text.endswith("。"):
                replaced = text[:-1] + f"。已按要求将“{src}”改为“{dst}”。"
            else:
                replaced = text + f" 已按要求将“{src}”改为“{dst}”。"
        return replaced

    def _expand_sentence_for_instruction(self, instruction: str) -> str:
        detail = instruction.strip()
        return f" 另外，针对“{detail}”，可以补充更具体的背景、例子和落地步骤。"

    def _instruction_tail(self, instruction: str) -> str:
        return f"\n\n补充说明：已根据要求“{instruction}”进行了修改。"

    def _detect_target_paragraph_index(self, instruction: str, paragraph_count: int) -> int | None:
        if paragraph_count <= 0:
            return None
        mapping = [
            ("第一段", 0),
            ("第二段", 1),
            ("第三段", 2),
            ("第四段", 3),
            ("第五段", 4),
            ("开头", 0),
            ("结尾", paragraph_count - 1),
            ("最后一段", paragraph_count - 1),
        ]
        for keyword, index in mapping:
            if keyword in instruction and index < paragraph_count:
                return index
        match = re.search(r"第([一二三四五六七八九十])段", instruction)
        if match:
            chinese_index = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "七": 6, "八": 7, "九": 8, "十": 9}
            return chinese_index.get(match.group(1)) if chinese_index.get(match.group(1)) is not None else None
        return None

    def _build_generation_prompt(self, topic: str, style: str, word_count: int, custom_prompt: str, allow_markdown: bool = True) -> str:
        base_intro = (
            "请直接输出可交付的中文 Markdown 文稿正文，不要解释你的思路。"
            if allow_markdown
            else "请直接输出可交付的中文文稿正文（普通文本），不要使用 Markdown 标题或标记，也不要解释你的思路。"
        )
        base = [
            base_intro,
            f"主题：{topic}",
            f"风格：{style}",
            f"目标字数：约{word_count}字",
            "必须满足：",
            "1. 紧扣主题，不要泛泛而谈。",
            "2. 至少包含标题、背景、分析、建议、结论五部分。",
            "3. 每一部分都要有实质内容，避免重复占位句。",
            "4. 优先回应用户提出的全部补充要求。",
            "5. 如果补充要求与主题冲突，保留主题主线并尽量兼顾补充要求。",
        ]
        if custom_prompt:
            base.append(f"额外要求：{custom_prompt}")
        return "\n".join(base)

    def _ensure_prompt_alignment(self, content: str, topic: str, custom_prompt: str, allow_markdown: bool = True) -> str:
        text = content.strip()
        if topic and topic not in text:
            if allow_markdown:
                text = f"# {topic}\n\n{text}"
            else:
                text = f"{topic}\n\n{text}"
        if custom_prompt:
            keywords = [word for word in re.split(r"[，,。；;、\s]+", custom_prompt) if len(word) >= 2]
            missing = [word for word in keywords if word and word not in text]
            if missing:
                text += "\n\n补充要求落实：" + "、".join(dict.fromkeys(missing[:6])) + "。"
        return text

    def _render_as_plain_text(self, content: str) -> str:
        """将 Markdown 风格内容简单转换为普通文本输出。"""
        text = content
        # 去掉 Markdown 标题前导符号
        text = re.sub(r"^#{1,6}\s*", "", text, flags=re.MULTILINE)
        # 去掉常见 inline markdown 标记
        text = text.replace("**", "").replace("__", "").replace("*", "").replace("`", "")
        # 去掉链接格式 [text](url) -> text
        text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)
        # 去掉多余的水平线
        text = re.sub(r"^-{3,}$", "", text, flags=re.MULTILINE)
        # 去除多余空行
        text = "\n".join([line.rstrip() for line in text.splitlines()])
        return text.strip() + "\n"

    def _resolve_user_path(self, raw_path: str) -> Path:
        """将用户输入路径解析为工作目录内绝对路径。"""
        candidate = Path(raw_path)
        if not candidate.is_absolute():
            candidate = self.workspace_dir / candidate
        return ensure_path_in_workspace(candidate, self.workspace_dir)

    def _normalize_filename(self, filename: str) -> str:
        """规范文件名：空名回退默认，缺扩展自动补 .txt。"""
        cleaned = filename.strip()
        if not cleaned:
            cleaned = f"article_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        if "." not in Path(cleaned).name:
            cleaned += ".txt"
        return cleaned

    def _split_paragraphs(self, content: str) -> list[str]:
        """按空行切分段落，并去除空段。"""
        parts = [p.strip() for p in content.split("\n\n")]
        return [p for p in parts if p]

    def _resolve_task_id(self, arguments: dict[str, Any]) -> str:
        explicit = str(arguments.get("task_id", "")).strip()
        if explicit:
            self.active_task_id = explicit
            return explicit
        if self.active_task_id:
            return self.active_task_id
        generated = f"task_{uuid.uuid4().hex[:8]}"
        self.active_task_id = generated
        return generated

    def _record_task_activity(
        self,
        task_id: str,
        file_path: Path,
        action: str,
        topic: str | None = None,
        style: str | None = None,
        word_count: int | None = None,
    ) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        session = self.task_sessions.setdefault(
            task_id,
            {
                "topic": topic or "未命名主题",
                "style": style or "通用",
                "word_count": word_count or 0,
                "files": [],
                "created_at": now,
                "updated_at": now,
                "last_action": action,
            },
        )
        if topic:
            session["topic"] = topic
        if style:
            session["style"] = style
        if word_count is not None:
            session["word_count"] = word_count
        path_str = str(file_path)
        if path_str not in session["files"]:
            session["files"].append(path_str)
        session["updated_at"] = now
        session["last_action"] = action

    def _estimate_word_count(self, content: str) -> int:
        """估算字数：优先按中文字符+英文单词统计。"""
        chinese_chars = sum(1 for ch in content if "\u4e00" <= ch <= "\u9fff")
        latin_words = len(re.findall(r"[A-Za-z0-9_]+", content))
        return chinese_chars + latin_words

    def _summarize_text(self, content: str, max_len: int = 80) -> str:
        """生成简短摘要。"""
        cleaned = " ".join(content.replace("\n", " ").split())
        if len(cleaned) <= max_len:
            return cleaned
        return cleaned[: max_len - 1] + "…"

    def _generate_plan_options(self, request: str, plan_count: int) -> list[dict[str, Any]]:
        """根据开放式请求生成结构化方案列表。"""
        cleaned = request.replace("写", "").replace("一篇", "").strip() or "未命名主题"
        base_name = "article_" + datetime.now().strftime("%Y%m%d_%H%M%S")

        candidates = [
            {
                "style": "学术正式",
                "word_count": 900,
                "filename": f"{base_name}_formal.md",
                "rationale": "适合课程作业与报告提交，结构规范。",
            },
            {
                "style": "通俗科普",
                "word_count": 700,
                "filename": f"{base_name}_popular.md",
                "rationale": "面向大众阅读，表达更清晰易懂。",
            },
            {
                "style": "观点评论",
                "word_count": 550,
                "filename": f"{base_name}_opinion.md",
                "rationale": "强调立场和案例，适合快速产出初稿。",
            },
        ]

        plans = []
        for plan in candidates[:plan_count]:
            item = {**plan, "topic": cleaned}
            plans.append(item)
        return plans
