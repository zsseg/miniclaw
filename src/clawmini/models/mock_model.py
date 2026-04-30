"""离线 Mock 模型：基于规则模拟 Function Calling，支持规划与多步执行。"""

from __future__ import annotations

import re
from pathlib import Path

from clawmini.core.security import ensure_path_in_workspace
from clawmini.models.base import BaseModelClient
from clawmini.types import AgentStep, Message, ToolCall


class MockModelClient(BaseModelClient):
    """用于本地开发与测试的规则模型，支持规划与多步执行。"""

    def __init__(self) -> None:
        super().__init__()
        self._execution_step: dict[str, int] = {}  # 按用户输入追踪执行到第几步

    def generate_step(self, messages: list[Message], tool_schemas: list[dict]) -> AgentStep:
        """根据用户最新输入做简化推理，支持规划与多步执行。"""
        if messages and messages[-1].role == "tool":
            return AgentStep(thought="工具已返回结果，整理为最终回复", final_answer=messages[-1].content)

        latest_user = next((m.content for m in reversed(messages) if m.role == "user"), "")

        # === 规划阶段检测 ===
        if "【规划指令】" in latest_user:
            return self._generate_plan(latest_user)

        # === 多步执行阶段：检查是否有未完成的计划 ===
        plan_result = self._try_multi_step_execution(latest_user)
        if plan_result is not None:
            return plan_result

        # === 单步操作匹配 ===
        if any(key in latest_user for key in ["QQ", "私聊", "群", "自动回复"]):
            return AgentStep(
                thought="检测到 QQ 自动回复需求，调用 QQ 工具执行。",
                action=ToolCall(
                    name="qq_auto_reply",
                    arguments={
                        "command": "handle_message",
                        "source": "group" if "群" in latest_user else "private",
                        "chat_id": "demo_chat",
                        "sender_id": "anon_user",
                        "text": latest_user,
                        "mentioned": "@我" in latest_user,
                        "mention_all": "@所有人" in latest_user,
                    },
                ),
            )

        writing_result = self._match_writing(latest_user)
        if writing_result is not None:
            return writing_result

        # 批量图片处理
        batch_keywords = ["批量处理", "批量调整", "批量转换", "resize", "调整尺寸", "转换格式", "重命名图片", "改尺寸"]
        if any(key in latest_user.lower() for key in batch_keywords):
            return AgentStep(
                thought="检测到批量图片处理请求，调用图像工具。",
                action=ToolCall(
                    name="image_batch_tool",
                    arguments={
                        "request": latest_user,
                        "input_dir": "images",
                        "output_dir": "output",
                        "target_format": "png",
                        "width": 1024,
                        "height": 768,
                        "overwrite": False,
                    },
                ),
            )

        # 绘画/文生图请求 —— 路由到 image_generation 工具
        draw_keywords = ["画", "绘制", "生成图片", "生成图像", "画一张", "画个", "画出", "创作", "文生图", "绘图", "生成一张"]
        if any(key in latest_user for key in draw_keywords):
            hints = self._extract_image_hints(latest_user)
            return AgentStep(
                thought="检测到绘画请求，调用 image_generation 工具生成图片或提示词。",
                action=ToolCall(
                    name="image_generation",
                    arguments={
                        "prompt": hints.get("prompt", latest_user),
                        "title": hints.get("title", ""),
                        "filename": hints.get("filename", ""),
                        "output_dir": hints.get("output_dir", ""),
                        "target_path": hints.get("target_path", ""),
                        "style": hints.get("style", "写实"),
                        "size": "1024x1024",
                        "n": 1,
                    },
                ),
            )

        # 设置/配置管理 —— 路由到 workspace_settings 工具
        settings_keywords = ["设置", "配置", "provider", "api_key", "api key", "base_url",
                              "model_provider", "model_name", "mock模式", "openai", "deepseek",
                              "qwen模式", "api密钥", "base url", "地址", "端口"]
        settings_actions = ["修改", "变更", "更改", "更新", "查看", "显示", "展示", "设为", "改成", "改为"]
        if any(k in latest_user.lower() for k in settings_keywords) and \
           any(a in latest_user for a in settings_actions):
            # 判断意图：是查看还是修改
            is_show = any(k in latest_user for k in ["查看", "显示", "展示", "当前设置", "现在的"])
            command = "show" if is_show else "update"
            # 提取 provider
            provider = "mock"
            for p in ["openai", "deepseek", "qwen", "mock"]:
                if p in latest_user.lower():
                    provider = p
                    break
            args = {"command": command}
            if command == "update":
                args["model_provider"] = provider
            return AgentStep(
                thought=f"检测到设置管理请求，调用 workspace_settings 工具。",
                action=ToolCall(name="workspace_settings", arguments=args),
            )

        # 会话管理 —— 路由到 workspace_session 工具
        session_keywords = ["会话", "session", "对话", "新会话", "切换会话",
                             "删除会话", "重命名会话", "列出会话"]
        session_actions = ["新建", "创建", "新", "切换", "选择", "打开", "列出",
                            "所有", "查看", "显示", "删除", "移除", "重命名", "改名"]
        if any(k in latest_user for k in session_keywords):
            # 判断操作类型
            if any(k in latest_user for k in ["新建", "创建", "新会话"]):
                session_cmd = "create"
                title = "新会话"
                import re as _re
                m = _re.search(r"(?:标题|title)\s*[为:：]?\s*([^\n，,；;]+)", latest_user)
                if m:
                    title = m.group(1).strip().lstrip("为").strip()
                args = {"command": "create", "title": title}
            elif any(k in latest_user for k in ["切换", "选择", "打开"]):
                session_cmd = "switch"
                args = {"command": "switch", "session_id": ""}
            elif any(k in latest_user for k in ["删除", "移除"]):
                session_cmd = "delete"
                args = {"command": "delete", "session_id": ""}
            elif any(k in latest_user for k in ["重命名", "改名"]):
                session_cmd = "rename"
                args = {"command": "rename", "session_id": "", "title": "重命名"}
            else:
                session_cmd = "list"
                args = {"command": "list"}
            return AgentStep(
                thought=f"检测到会话管理请求，调用 workspace_session 工具。",
                action=ToolCall(name="workspace_session", arguments=args),
            )

        file_result = self._match_file_operation(latest_user)
        if file_result is not None:
            return file_result

        if "shell" in latest_user.lower() or "命令" in latest_user:
            return AgentStep(
                thought="检测到命令执行请求，调用安全 shell 工具。",
                action=ToolCall(
                    name="run_shell_command",
                    arguments={
                        "command": "python",
                        "args": ["-c", "print('hello from shell tool')"],
                        "timeout_sec": 5,
                    },
                ),
            )

        if re.search(r"(你好|hi|hello)", latest_user, flags=re.IGNORECASE):
            return AgentStep(thought="常规问候，无需工具。", final_answer="你好，我是 Clawmini，可以帮你处理 QQ、文稿和图片任务。")

        return AgentStep(thought="未命中工具，直接答复。", final_answer="我已收到请求。若要执行操作，请明确说明 QQ、文稿或图片任务。")

    def _generate_plan(self, latest_user: str) -> AgentStep:
        """生成多步执行计划。"""
        # 提取原始用户需求
        user_req = latest_user.replace("【规划指令】", "").replace("请分析这个需求，输出一个具体的多步执行计划。", "").strip()
        plan_lines = [f"📋 已分析需求，制定以下执行计划："]

        # 分析需求中包含的操作类型
        operations = self._analyze_operations(user_req)
        for i, op in enumerate(operations, 1):
            plan_lines.append(f"{i}. {op}")

        if not operations:
            plan_lines.append("1. 自动识别需求并执行对应操作")

        plan_lines.append("\n开始逐步执行...")
        return AgentStep(thought="已生成执行计划", final_answer="\n".join(plan_lines))

    def _analyze_operations(self, text: str) -> list[str]:
        """分析文本中包含的多种操作，返回操作步骤列表。"""
        ops: list[str] = []

        # 检测写作需求
        if any(k in text for k in ["文稿", "文章", "写一篇", "写作", "写一个"]):
            if "方案" in text or "计划" in text or "草稿" in text:
                ops.append("生成多个候选方案供用户选择")
            else:
                style = "正式" if "正式" in text else ("幽默" if "幽默" in text else "通用")
                word_count = "800字" if "800" in text else "300字"
                ops.append(f"创建{style}风格、{word_count}的文稿文件")

        # 检测文件操作
        if any(k in text for k in ["创建", "新建", "生成文件"]):
            ops.append("在工作区创建新文件")
        if "修改" in text or "编辑" in text or "替换" in text:
            ops.append("编辑或修改文件内容")
        if "追加" in text:
            ops.append("向文件追加内容")
        if "删除" in text or "移除" in text:
            ops.append("安全删除文件（移入回收站）")
        if "重命名" in text or "改名" in text:
            ops.append("重命名文件")
        if "移动" in text:
            ops.append("移动文件")
        if "列出" in text or "查看" in text or "目录" in text:
            ops.append("列出工作区文件")
        if "读取" in text:
            ops.append("读取文件内容")

        # 检测图片处理
        batch_words = ["批量处理", "批量调整", "批量转换", "resize", "调整尺寸", "转换格式", "重命名图片", "改尺寸"]
        if any(k in text.lower() for k in batch_words):
            ops.append("批量处理图片（尺寸/格式/重命名）")

        # 检测 QQ 操作
        if "QQ" in text or "私聊" in text or "群" in text or "自动回复" in text:
            ops.append("配置或执行 QQ 自动回复")

        # 检测绘画请求
        draw_words = ["画", "绘制", "生成图片", "生成图像", "创作", "文生图", "绘图"]
        if any(k in text for k in draw_words):
            ops.append("文生图：根据描述生成图片或画面提示词")

        return ops

    def _try_multi_step_execution(self, latest_user: str) -> AgentStep | None:
        """检测复杂需求并返回多步执行中的当前步骤。"""
        # 复合操作：写作 + 文件操作同时存在
        has_writing = any(k in latest_user for k in ["文稿", "文章", "写一篇", "写作", "写一个", ".md", ".txt"])
        has_file_op = any(k in latest_user for k in ["创建", "删除", "重命名", "移动", "列出", "修改", "编辑", "替换", "追加"])
        has_batch = any(k in latest_user.lower() for k in ["批量处理", "批量调整", "批量转换", "resize", "调整尺寸", "转换格式"])
        has_draw = any(k in latest_user for k in ["画", "绘制", "文生图", "绘图"])
        has_qq = any(k in latest_user for k in ["QQ", "私聊", "群", "自动回复"])

        # 统计有多少种操作
        operation_count = sum([has_writing, has_file_op, has_batch, has_draw, has_qq])

        # 如果只有一种操作类型，交给单步匹配
        if operation_count <= 1:
            return None

        # 复杂需求：逐步执行，用 session 追踪进度
        session_key = latest_user[:40]  # 用输入前40字符作为 key
        step = self._execution_step.get(session_key, 0)
        self._execution_step[session_key] = step + 1

        ordered_ops: list[tuple[str, str, dict]] = []

        if has_qq:
            ordered_ops.append((
                "qq_auto_reply",
                "正在配置QQ自动回复...",
                {
                    "command": "handle_message",
                    "source": "group" if "群" in latest_user else "private",
                    "chat_id": "demo_chat",
                    "sender_id": "anon_user",
                    "text": latest_user,
                    "mentioned": "@我" in latest_user,
                    "mention_all": "@所有人" in latest_user,
                },
            ))
        if has_writing:
            ordered_ops.append((
                "writing_tool",
                "正在生成文稿...",
                {
                    "command": "create",
                    "topic": latest_user,
                    "style": "正式" if "正式" in latest_user else "通用",
                    "word_count": 800 if "800" in latest_user else 300,
                    "filename": "article_auto.md",
                },
            ))
        if has_file_op:
            if "删除" in latest_user:
                cmd = "delete"
            elif "重命名" in latest_user or "改名" in latest_user:
                cmd = "rename"
            elif "创建" in latest_user or "新建" in latest_user or "生成文件" in latest_user:
                cmd = "create"
            elif "修改" in latest_user or "编辑" in latest_user or "替换" in latest_user or "追加" in latest_user:
                cmd = "write"
            elif "列出" in latest_user or "查看" in latest_user or "目录" in latest_user:
                cmd = "list"
            else:
                cmd = "read"
            ordered_ops.append((
                "workspace_files",
                "正在执行文件操作...",
                {
                    "command": cmd,
                    "path": "workspace_demo.txt",
                    "source_path": "workspace_demo.txt",
                    "target_path": "workspace_demo_renamed.txt" if cmd == "rename" else "",
                    "content": f"根据用户请求生成的内容：{latest_user}" if cmd in {"create", "write"} else "",
                    "overwrite": True,
                },
            ))
        if has_batch:
            ordered_ops.append((
                "image_batch_tool",
                "正在批量处理图片...",
                {
                    "request": latest_user,
                    "input_dir": "images",
                    "output_dir": "output",
                    "target_format": "png",
                    "width": 1024,
                    "height": 768,
                    "overwrite": False,
                },
            ))
        if has_draw:
            style = "写实"
            if "二次元" in latest_user or "动漫" in latest_user:
                style = "二次元"
            elif "水彩" in latest_user:
                style = "水彩"
            elif "油画" in latest_user:
                style = "油画"
            elif "素描" in latest_user:
                style = "素描"
            elif "国风" in latest_user or "水墨" in latest_user:
                style = "国风"
            ordered_ops.append((
                "image_generation",
                "正在生成图片/画面描述...",
                {
                    "prompt": latest_user,
                    "style": style,
                    "size": "1024x1024",
                    "n": 1,
                },
            ))

        if step >= len(ordered_ops):
            # 所有步骤已完成
            self._execution_step.pop(session_key, None)
            return AgentStep(
                thought="所有操作已完成，整理结果。",
                final_answer=f"所有操作已完成！共执行了 {len(ordered_ops)} 个步骤。",
            )

        op = ordered_ops[step]
        return AgentStep(
            thought=f"【步骤 {step + 1}/{len(ordered_ops)}】{op[1]}",
            action=ToolCall(name=op[0], arguments=op[2]),
        )

    def _extract_image_hints(self, text: str) -> dict[str, str]:
        """从自然语言中提取文生图标题、路径和文件名。"""
        def _pick(patterns: list[str]) -> str:
            for pattern in patterns:
                match = re.search(pattern, text, flags=re.IGNORECASE)
                if match:
                    value = match.group(1).strip().strip('"\'')
                    if value:
                        return value
            return ""

        style = "写实"
        if "二次元" in text or "动漫" in text or "日系" in text:
            style = "二次元"
        elif "水彩" in text:
            style = "水彩"
        elif "油画" in text:
            style = "油画"
        elif "素描" in text or "铅笔" in text:
            style = "素描"
        elif "国风" in text or "水墨" in text or "中国风" in text:
            style = "国风"

        title = _pick([
            r"(?:标题|题目|标题名)[:：]\s*([^\n，,；;]+)",
            r"(?:主题|主题名)[:：]\s*([^\n，,；;]+)",
        ])
        filename = _pick([
            r"(?:文件名|图片名)[:：]\s*([^\n，,；;]+)",
        ])
        target_path = _pick([
            r"(?:保存到|路径|保存路径|目标路径)[:：]\s*([^\n，；;]+)",
        ])
        output_dir = ""
        if target_path:
            try:
                path = Path(target_path)
                if path.suffix:
                    output_dir = str(path.parent)
                    if not filename:
                        filename = path.name
                else:
                    output_dir = target_path
            except Exception:
                output_dir = ""

        if not filename and title:
            filename = f"{re.sub(r'[^\w\u4e00-\u9fff-]+', '_', title).strip('_')}.png"

        return {
            "style": style,
            "title": title,
            "filename": filename,
            "output_dir": output_dir,
            "target_path": target_path,
            "prompt": text,
        }

    def _extract_writing_hints(self, text: str) -> dict[str, str]:
        """从自然语言中提取文稿文件名、目录和补充要求。"""
        def _pick(patterns: list[str]) -> str:
            for pattern in patterns:
                match = re.search(pattern, text, flags=re.IGNORECASE)
                if match:
                    value = match.group(1).strip().strip('"\'')
                    if value:
                        return value
            return ""

        style = "通用"
        if any(k in text for k in ["正式", "学术", "论文", "分析"]):
            style = "正式"
        elif any(k in text for k in ["科普", "说明"]):
            style = "科普"
        elif any(k in text for k in ["幽默", "轻松"]):
            style = "幽默"

        filename = _pick([
            r"(?:文件名|文稿名|保存文件名)[:：]\s*([^\s，,；;\\/]+?\.(?:md|txt|docx?))",
            r"(?:生成文稿|写文稿|创建文稿|生成文章|写文章|生成文件|写文件)\s*([^\s，,；;\\/]+?\.(?:md|txt|docx?))",
        ])
        if not filename:
            filename_matches = re.findall(r"([^\s，,；;\\/]+?\.(?:md|txt|docx?))", text, flags=re.IGNORECASE)
            filename = filename_matches[-1].strip().strip('"\'') if filename_matches else ""
        output_dir = _pick([
            r"(?:输出目录|保存目录|保存到目录)[:：]\s*([^\n，,；;]+)",
            r"(?:在|到|保存到|输出到)\s*([^\n，,；;]+?)\s*(?:生成文稿|写文稿|创建文稿|生成文章|写文章)",
            r"在([^\n，,；;]+?)文件夹",
        ])
        target_path = _pick([
            r"(?:保存到|路径|保存路径|目标路径)[:：]\s*([^\n，；;]+)",
        ])
        content = _pick([
            r"(?:内容是|内容|正文是|要求是)[:：]\s*(.+)$",
        ])
        if not content:
            content = text

        if target_path:
            try:
                path = Path(target_path)
                if path.suffix:
                    output_dir = str(path.parent)
                    if not filename:
                        filename = path.name
                else:
                    output_dir = target_path
            except Exception:
                pass

        if output_dir.endswith("文件夹"):
            output_dir = output_dir[:-3].strip()
        if output_dir.endswith("目录"):
            output_dir = output_dir[:-2].strip()

        if not filename and any(k in text for k in [".md", ".txt", ".doc", ".docx"]):
            file_match = re.search(r"([\w\-.\u4e00-\u9fff]+\.(?:md|txt|docx?))", text, flags=re.IGNORECASE)
            if file_match:
                filename = file_match.group(1)

        return {
            "style": style,
            "filename": filename,
            "output_dir": output_dir,
            "target_path": target_path,
            "custom_prompt": content,
        }

    def _match_writing(self, text: str) -> AgentStep | None:
        """匹配文稿写作需求。"""
        if not any(k in text for k in ["文稿", "文章", "写一篇", "写作", ".md", ".txt"]):
            return None

        hints = self._extract_writing_hints(text)

        has_word_target = any(ch.isdigit() for ch in text)
        has_filename = bool(hints.get("filename")) or ".md" in text or ".txt" in text
        has_style_hint = any(k in text for k in ["正式", "幽默", "技术", "学术", "科普"])
        if not has_word_target and not has_filename and not has_style_hint:
            return AgentStep(
                thought="检测到开放式写作请求，先输出 2-3 个候选方案供用户选择。",
                action=ToolCall(
                    name="writing_tool",
                    arguments={
                        "command": "brainstorm_plans",
                        "request": text,
                        "plan_count": 3,
                    },
                ),
            )

        word_count = 800 if "800" in text else 300
        return AgentStep(
            thought="检测到文稿生成请求，调用写作工具创建文件。",
            action=ToolCall(
                name="writing_tool",
                arguments={
                    "command": "create",
                    "topic": hints.get("custom_prompt", text),
                    "style": hints.get("style", "正式" if "正式" in text else "通用"),
                    "word_count": word_count,
                    "filename": hints.get("filename", "article_auto.md") or "article_auto.md",
                    "output_dir": hints.get("output_dir", "") or ".",
                    "custom_prompt": hints.get("custom_prompt", text),
                },
            ),
        )

    def _match_file_operation(self, text: str) -> AgentStep | None:
        """匹配工作区文件操作需求。"""
        file_keywords = ["创建", "新建", "生成文件", "修改", "编辑", "替换", "追加", "删除", "移除", "重命名", "改名", "移动", "列出", "查看", "读取", "文件", "文件夹", "目录"]
        if not any(keyword in text for keyword in file_keywords):
            return None

        command = "read"
        if any(keyword in text for keyword in ["删除", "移除"]):
            command = "delete"
        elif any(keyword in text for keyword in ["重命名", "改名", "移动"]):
            command = "rename"
        elif any(keyword in text for keyword in ["创建", "新建", "生成文件"]):
            command = "create"
        elif any(keyword in text for keyword in ["修改", "编辑", "替换", "追加"]):
            command = "write"
        elif any(keyword in text for keyword in ["列出", "查看", "目录"]):
            command = "list"

        path_match = re.search(r"([\w.\\/-]+\.[A-Za-z0-9]+|[\w.\\/-]+)", text)
        path = path_match.group(1) if path_match else "workspace_demo.txt"
        target_path = path.replace(".txt", "_renamed.txt") if command == "rename" else ""
        content = f"根据用户请求生成的内容：{text}" if command in {"create", "write"} else ""
        return AgentStep(
            thought="检测到工作区文件操作请求，调用工作区文件工具。",
            action=ToolCall(
                name="workspace_files",
                arguments={
                    "command": command,
                    "path": path,
                    "source_path": path,
                    "target_path": target_path,
                    "content": content,
                    "overwrite": True,
                },
            ),
        )
