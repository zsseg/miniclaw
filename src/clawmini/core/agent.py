"""智能体总控模块：装配模型、工具与 ReAct。"""

from __future__ import annotations

import json
import re
from typing import Any, Callable

from clawmini.config import AgentConfig
from clawmini.core.memory import ConversationMemory
from clawmini.core.react_loop import ReactLoop, ReactRunResult
from clawmini.core.sub_agents import FileAnalysisAgent
from clawmini.models.base import BaseModelClient
from clawmini.models.deepseek_model import DeepSeekModelClient
from clawmini.models.mock_model import MockModelClient
from clawmini.models.openai_model import OpenAIModelClient
from clawmini.models.qwen_model import QwenModelClient
from clawmini.storage.history_store import HistoryStore
from clawmini.tools.image_batch_tool import ImageBatchTool
from clawmini.tools.image_gen_tool import ImageGenerationTool
from clawmini.tools.pdf_gen_tool import DocumentGenerationTool
from clawmini.tools.pdf_reader_tool import PdfReaderTool
from clawmini.tools.qq_auto_reply import QQAutoReplyTool
from clawmini.tools.registry import ToolRegistry
from clawmini.tools.session_manager_tool import SessionManagerTool
from clawmini.tools.settings_tool import SettingsTool
from clawmini.tools.shell_tool import ShellCommandTool
from clawmini.tools.workspace_file_tool import WorkspaceFileTool
from clawmini.tools.writing_tool import WritingTool
from clawmini.types import Message

# ── 通用的系统提示词模板 ──────────────────────────────────────
SYSTEM_PROMPT_TEMPLATE = """\
你是 Clawmini 的规划器，负责理解用户的自然语言需求并调用合适的工具完成。

## 输出格式
必须输出纯 JSON（不要包含 ```json 或其他标记），格式如下：
{{"thought": str, "action": str|null, "arguments": object, "final_answer": str|null}}

- thought：你对用户需求的分析
- action：要调用的工具名称（null 表示直接给出最终回答）
- arguments：传给工具的参数对象
- final_answer：最终回答（非空时结束本轮推理）

## 可用的工具
{tool_descriptions}

## 核心原则
1. 用户可能要求：操作文件、生成图片、撰写文稿、管理会话、修改设置、执行命令等
2. 分析用户需求后选择最合适的工具，如果涉及多个步骤，一次只调用一个工具
3. 工具执行后，根据返回结果组织最终回答给用户
4. 涉及会话管理（新建/切换/删除/重命名/列出），调用 workspace_session 工具
5. 涉及修改 API 设置（provider/key/model/base_url），调用 workspace_settings 工具的 update 命令
6. 涉及查看当前设置，调用 workspace_settings 工具的 show 命令
7. 完成所有操作后务必填写 final_answer，不要留空
8. 所有路径都在工作区内，不要使用工作区外的路径"""

# ── 纯聊天的系统提示词（无工具） ─────────────────────────────
CHAT_SYSTEM_PROMPT = """\
你是 Clawmini，一个智能助手。请与用户进行自然、友好的对话。
回答时不要提及「工具」、「调用」、「ReAct」等系统内部机制，直接以自然语言回复用户的问题。
如果用户要求操作文件、生成图片等具体任务，请告知用户切换到「任务模式」使用。
请用中文回复。"""

# ── 意图检测：两阶段方案 ─────────────────────────────
# 阶段一：关键词快速判定
# 阶段二：API 兜底（关键词冲突 / 无法确定时）

# 明确表示聊天的关键词（快速判聊天，不走工具）
_CHAT_KEYWORDS = [
    "你好", "您好", "嗨", "哈喽", "hello", "hi",
    "天气", "今天天气", "明天天气",
    "讲个故事", "讲个笑话", "唱首歌", "聊天", "闲聊",
    "今天心情", "你叫什么", "你是谁", "你能做什么",
    "谢谢你", "感谢", "晚安", "早安", "下午好",
    "最近怎么样", "在吗", "在不在",
]

# 明确表示工具/文件操作的关键词（快速判工具，不走 API）
_TOOL_KEYWORDS = [
    "创建文件", "新建文件", "编辑文件", "修改文件", "删除文件", "重命名文件",
    "写入文件", "追加内容", "读取文件", "查看文件", "列出文件", "目录",
    "写一篇", "写作", "文稿", "文章", "生成文稿",
    "生成图片", "绘制", "文生图", "绘图", "生成一张",
    "帮我画", "给我画", "帮我生成",
    "QQ自动回复", "QQ私聊", "QQ群", "私聊", "自动回复",
    "批量处理", "批量调整", "批量转换", "resize", "调整尺寸", "转换格式",
    "shell", "执行命令", "终端命令",
    "新建会话", "切换会话", "删除会话", "重命名会话",
    "查看设置", "修改设置", "更新设置", "API设置", "当前设置",
    "分析文件",
    # 补充遗漏的文件操作句式
    "改名为", "改成", "改名", "重命名",
    "创建", "新建", "新建文件", "建立",
    "写入", "写 ", "写入文件",
    "删除 ", "删除文件",
    "读取", "查看文件",
]

# 祈使句 + 动作动词 → 启发式判工具
# 用于关键词未命中但句式明显是请求 AI 执行某操作的场景
_IMPERATIVE_PREFIXES = ["帮我", "给我", "我要", "请帮我", "请给我", "替我"]
_ACTION_VERBS = ["画", "创建", "生成", "写", "写一篇", "制作", "转换", "调整", "修改", "删除", "重命名", "读取"]

# 既有工具词也有聊天词时，用此 prompt 让 API 做最终判断
_INTENT_CLASSIFY_PROMPT = """\
你是一个意图分类器。判断用户输入意图是 "chat"（聊天、问候、情感交流、闲聊、问百科知识）还是 "tool"（需要编辑/读取/创建文件、生成图片、操作QQ、执行命令、管理设置等）。
只返回一个词 "chat" 或 "tool"，不要返回其他内容。

用户输入：{user_text}
意图："""


def _is_chat_keyword(text: str) -> bool:
    """阶段一：明确聊天词 → 判聊天。"""
    lowered = text.lower()
    return any(kw in lowered for kw in _CHAT_KEYWORDS)


def _is_tool_keyword(text: str) -> bool:
    """阶段一：明确工具词 → 判工具。"""
    lowered = text.lower()
    return any(kw in lowered for kw in _TOOL_KEYWORDS)


def _heuristic_tool_intent(text: str) -> bool:
    """启发式规则：检测祈使句+动作动词模式 → 判工具。

    捕捉 "帮我画一只猫"、"给我生成一张图" 等关键词未覆盖的句型。
    """
    lowered = text.lower()
    for prefix in _IMPERATIVE_PREFIXES:
        if prefix not in lowered:
            continue
        # 找到祈使前缀后的动词
        idx = lowered.index(prefix) + len(prefix)
        remainder = lowered[idx:].strip()
        for verb in _ACTION_VERBS:
            if remainder.startswith(verb) or verb in remainder[:10]:
                return True
    return False


def _api_classify_intent(text: str, model_client: BaseModelClient | None) -> bool:
    """阶段二：调用 API 判断是否为聊天意图。返回 True=聊天, False=工具。"""
    if model_client is None or not hasattr(model_client, "chat_direct"):
        # 没有模型客户端或模型不支持，按不含工具词处理
        return True
    prompt = _INTENT_CLASSIFY_PROMPT.format(user_text=text)
    try:
        reply = model_client.chat_direct([{"role": "user", "content": prompt}])
        reply = reply.strip().lower()
        return reply != "tool"  # 默认 chat
    except Exception:
        return True  # 出错时保守走聊天


def _is_chat_intent(text: str, model_client: BaseModelClient | None = None) -> bool:
    """检测用户输入是否为纯聊天（无需工具）。

    两阶段：
    1. 关键词快速判定
    2. 模糊时 API 兜底
    """
    # 空文本视为聊天
    if not text.strip():
        return True

    # 阶段一：关键词快速判定
    if _is_tool_keyword(text):
        return False  # 明确工具意图
    if _is_chat_keyword(text):
        return True   # 明确聊天意图

    # 阶段一·五：启发式规则 — 祈使句 + 动作动词 → 判工具
    # 覆盖 "帮我画一只猫"、"给我生成一张图" 等
    if _heuristic_tool_intent(text):
        return False

    # 阶段二：API 兜底（需要额外的模型判断，且模型需支持 chat_direct）
    # Mock 模型或无 API 时，启发式已覆盖主要工具句式，剩余视为聊天
    if model_client is None or isinstance(model_client, MockModelClient):
        return True
    return _api_classify_intent(text, model_client)


def _build_chat_messages(user_text: str, history_messages: list[Message]) -> list[dict]:
    """为纯聊天构建消息列表（不含工具 schema 的普通对话）。"""
    result = [{"role": "system", "content": CHAT_SYSTEM_PROMPT}]
    # 取最近的历史（跳过旧的 system 和 tool 消息）
    for m in history_messages:
        if m.role in ("user", "assistant"):
            result.append({"role": m.role, "content": m.content})
    result.append({"role": "user", "content": user_text})
    return result


class ClawminiAgent:
    """Clawmini 智能体。"""

    def __init__(self, config: AgentConfig, session_manager: Any = None) -> None:
        self.config = config
        self.config.ensure_workspace()
        self._session_manager = session_manager

        self.memory = ConversationMemory()
        self.history_store = HistoryStore(config.history_path)
        self.memory.messages.extend(self.history_store.load())
        self.file_analysis_agent = FileAnalysisAgent(workspace_dir=config.workspace_dir)

        self.registry = ToolRegistry()
        self._register_tools()

        self.model_client = self._build_model_client()
        self.react_loop = ReactLoop(self.model_client, self.registry, max_rounds=config.max_rounds)

        # 注入 system prompt（放在 messages 最前面）
        self._ensure_system_prompt()

    def _build_system_prompt(self) -> str:
        """根据当前注册的工具动态构建 system prompt。"""
        tool_schemas = self.registry.describe_tools()
        tool_descriptions = json.dumps(tool_schemas, ensure_ascii=False, indent=2)
        return SYSTEM_PROMPT_TEMPLATE.format(tool_descriptions=tool_descriptions)

    def _ensure_system_prompt(self) -> None:
        """确保 memory 中第一条 message 是最新的 system prompt。"""
        system_content = self._build_system_prompt()
        if self.memory.messages and self.memory.messages[0].role == "system":
            self.memory.messages[0] = Message(role="system", content=system_content)
        else:
            self.memory.messages.insert(0, Message(role="system", content=system_content))

    def rebuild_for_settings_change(self) -> None:
        """设置变更后重建模型客户端（保留历史消息）。"""
        old_messages = list(self.memory.messages)
        self.model_client = self._build_model_client()
        self.react_loop = ReactLoop(self.model_client, self.registry, max_rounds=self.config.max_rounds)
        self.memory.messages = old_messages
        self._ensure_system_prompt()

    def _register_tools(self) -> None:
        """注册业务工具。"""
        self.registry.register(QQAutoReplyTool(workspace_dir=self.config.workspace_dir))
        self.registry.register(WritingTool(workspace_dir=self.config.workspace_dir))
        self.registry.register(WorkspaceFileTool(workspace_dir=self.config.workspace_dir))
        self.registry.register(ImageBatchTool(workspace_dir=self.config.workspace_dir))
        self.registry.register(ShellCommandTool(workspace_dir=self.config.workspace_dir))

        # 注册文生图工具，传入 API Key
        img_gen = ImageGenerationTool(
            workspace_dir=self.config.workspace_dir,
            api_key=self.config.api_key,
        )
        self.registry.register(img_gen)

        # 注册会话管理工具（如果有 session manager）
        session_tool = SessionManagerTool(workspace_dir=self.config.workspace_dir)
        if self._session_manager is not None:
            session_tool.set_session_manager(self._session_manager)
        self.registry.register(session_tool)

        # 注册文档生成工具（PDF/PPT/图文合成）
        self.registry.register(DocumentGenerationTool(workspace_dir=self.config.workspace_dir))

        # 注册 PDF 智能阅读工具（扫描版/文字版，带视觉 LLM 理解）
        pdf_reader = PdfReaderTool(
            workspace_dir=self.config.workspace_dir,
            api_key=self.config.api_key,
            base_url=self.config.base_url or "https://dashscope.aliyuncs.com/compatible-mode/v1",
            model=self.config.model_name or "qwen-vl-plus",
        )
        self.registry.register(pdf_reader)

        # 注册设置管理工具（如果有 session manager）
        settings_tool = SettingsTool(workspace_dir=self.config.workspace_dir)
        if self._session_manager is not None:
            settings_tool.set_session_manager(self._session_manager)
        self.registry.register(settings_tool)

        if self.config.tool_plugins_config is not None:
            self.registry.load_from_config(self.config.tool_plugins_config, workspace_dir=self.config.workspace_dir)

    def _build_model_client(self) -> BaseModelClient:
        """根据配置构造模型客户端。"""
        provider = self.config.model_provider
        if provider == "openai":
            return OpenAIModelClient(self.config)
        if provider == "deepseek":
            return DeepSeekModelClient(self.config)
        if provider == "qwen":
            return QwenModelClient(self.config)
        return MockModelClient()

    def handle_user_input(self, user_text: str) -> str:
        """处理用户输入并返回最终回答。"""
        result = self.handle_user_input_verbose(user_text)
        return result.final_answer

    def handle_user_input_verbose(
        self,
        user_text: str,
        event_callback: Callable[[str], None] | None = None,
    ) -> ReactRunResult:
        """处理用户输入并返回回答。

        自动检测意图：
        - 纯聊天 → 绕过 ReAct，直接调用模型对话
        - 文件/工具操作 → 进入 ReAct 循环
        """
        self._ensure_system_prompt()

        # ── 检测是否为纯聊天 ──
        if _is_chat_intent(user_text, model_client=self.model_client):
            return self._chat_direct(user_text, event_callback=event_callback)

        # ── 工具/任务模式 ──
        self.memory.add("user", user_text)

        delegated = self._try_delegate(user_text)
        if delegated is not None:
            self.memory.add("assistant", delegated)
            result = ReactRunResult(final_answer=delegated, rounds=0, traces=["SubAgent delegated: file-analysis"])
            if event_callback is not None:
                event_callback(result.traces[0])
            self.history_store.save(self.memory.messages)
            return result

        # 直接执行：ReAct 循环自主决策
        if event_callback is not None:
            event_callback("🤔 AI 正在分析需求并调用合适的工具...")
        result = self.react_loop.run(self.memory, event_callback=event_callback)
        self.history_store.save(self.memory.messages)
        return result

    def _chat_direct(
        self,
        user_text: str,
        event_callback: Callable[[str], None] | None = None,
    ) -> ReactRunResult:
        """纯聊天：直接调用模型，不经过 ReAct 循环。"""
        # mock 模型不支持聊天，回退到 ReAct（mock 下也返回 mock 回复）
        if isinstance(self.model_client, MockModelClient):
            if event_callback is not None:
                event_callback("🤔 AI 正在处理...")
            self.memory.add("user", user_text)
            result = self.react_loop.run(self.memory, event_callback=event_callback)
            self.history_store.save(self.memory.messages)
            return result

        if event_callback is not None:
            event_callback("💬 AI 正在回复...")

        try:
            chat_messages = _build_chat_messages(user_text, self.memory.messages)
            reply = self.model_client.chat_direct(chat_messages)
            self.memory.add("user", user_text)
            self.memory.add("assistant", reply)
            self.history_store.save(self.memory.messages)
            return ReactRunResult(final_answer=reply, rounds=0, traces=["Chat direct"])
        except Exception as exc:
            err = f"❌ 聊天回复失败：{exc}"
            return ReactRunResult(final_answer=err, rounds=0, traces=[err])

    def _try_delegate(self, user_text: str) -> str | None:
        """主 Agent 委托子 Agent（雏形）。"""
        match = re.search(r"分析文件\s+(.+)$", user_text.strip())
        if not match:
            return None
        raw_path = match.group(1).strip().strip("\"'")
        return self.file_analysis_agent.analyze_file(raw_path)
