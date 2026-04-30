# Clawmini 工作区助手

Clawmini 是一款运行在电脑桌面上的轻量化 AI 助手（基于 Tkinter GUI），目标是在本地与大模型结合下方便地执行文件管理、文稿与图片生成、以及 QQ 自动回复等日常任务。

本 README 概述：功能 · 启动 · GUI 构建细节 · 核心架构 · 常见故障排查（含 QQ 自动填充）

---

## 主要功能一览

| 功能 | 说明 |
|------|------|
| **📁 文件管理** | 在 `workspace/` 内创建/读取/写入/重命名/删除文件（删除进入回收，可恢复） |
| **📝 文稿撰写** | 使用写作工具生成草稿、段落预览、提交与撤销，支持批量与队列任务 |
| **🖼️ 图片生成** | 集成图像生成工具（通义万相或其它服务），支持单张与批量处理 |
| **🔍 联网搜索** | 可开启 DeepSeek / Qwen 的联网检索，用于获取时效性信息 |
| **💬 QQ 自动回复** | 在工具层集成 QQ 自动化适配器，可模拟/托管或通过 NapCat 填充发送消息 |
| **🗂️ 多会话管理** | 会话分离、历史持久化、切换与导出 |
| **🧠 智能意图识别** | 三层判定：关键词 → 启发式（祈使+动词）→ 模型 API 兜底 |

---

## 快速启动

```powershell
cd 项目目录
python app.py
```

首次启动会在项目根下创建 `workspace/` 目录并生成必要文件（`app_state.json`、`sessions/` 等）。GUI 启动后即可通过输入框与 AI 对话或使用右上角齿轮打开设置。

---

## GUI（py 窗口）构建与运行流程

核心 GUI 文件：`app.py`。

窗口基于 Tkinter 构建，主要组件与交互逻辑：

- 主容器：分为左侧会话列表、右侧功能标签页（文件管理 / QQ 自动回复 / 图片任务等）、底部消息输入区。
- 输入框：支持 `Ctrl+Enter` 发送；支持草稿模式（draft_followup）用于对已有文件的补充修改。
- 发送流程：用户按发送触发 `on_send()` → 将消息推入 UI 聊天窗并调用 `_run_async('agent_message', {'text': text})`。
- 后台线程：`_worker()` 在后台线程中执行 `agent.handle_user_input_verbose()`，并通过 `response_queue` 将轨迹（trace）与最终回答推回主线程显示，避免阻塞 UI。
- 进度反馈：长任务（如图片生成）通过 `event_callback` 回传中间进度并显示在轨迹面板。
- 设置面板：通过齿轮打开，可配置模型提供商、API Key、模型名、Enable Search（联网搜索开关）等。设置变更会调用 `agent.rebuild_for_settings_change()` 重建模型客户端。

实现要点：GUI 与 Agent 通过线程安全的 `queue.Queue` 进行通信，所有耗时操作都在后台线程执行，确保主线程（Tkinter）不被阻塞。

---

## 核心架构与执行流程

- `AgentConfig`：集中配置（model_provider, model_name, api_key, base_url, enable_search, workspace_dir 等）。
- `ClawminiAgent`（`src/clawmini/core/agent.py`）：
	- 初始化模型客户端（`MockModelClient` / `OpenAIModelClient` / `QwenModelClient` / `DeepSeekModelClient`）
	- 注册工具（`WorkspaceFileTool`, `WritingTool`, `ImageGenerationTool`, `QQAutoReplyTool`, 等）到 `ToolRegistry`
	- 使用 `ConversationMemory` 与 `HistoryStore` 维护对话历史
	- 意图检测：先关键词、再启发式（祈使句+动作动词），最后在模糊场景用模型 API 兜底

- ReAct 循环（`ReactLoop`）：多轮生成 `Thought` → `Action` → 执行工具（由 `ToolRegistry`）→ 返回 `Observation`，直到返回 `final_answer` 或达到最大轮数

---

## QQ 自动填充（Auto-fill / 一键填充）说明与排查

工作原理概述：

- `qq_auto_reply` 工具（`src/clawmini/tools/qq_auto_reply.py`）负责把智能体的回复或模板转换为 QQ 消息并触发发送。发送方式支持：
	- `mock`：仅日志/模拟，不连接真实 QQ
	- `managed` / `windows`：通过 NapCat 或 Windows 自动化实现一键填充与发送

常见问题与排查：

1. 自动填充失效：
	 - 检查 NapCat 是否已经安装并运行（若使用 NapCat 模式）。
	 - 在设置中确认 `gateway_mode` 与 `target_group_id` 配置正确。
	 - 查看 `workspace/qq_auto_reply.log` 获取错误与回退信息。

2. Windows 自动化失败：
	 - 可能因目标窗口不可见或权限不足，尝试以管理员身份运行程序或 NapCat。
	 - 工具会在初始化失败时回退到 `mock` 模式，检查日志确认回退原因。

3. 若自动填充逻辑需要调试：
	 - 在设置里临时切换到 `mock` 模式以验证消息生成逻辑而不执行发送。
	 - 使用「模拟收到消息」按钮测试回复策略。

---

## 设置 & 高级选项

- 在 GUI 设置或通过命令行命令进行：
	- `/settings api_key=sk-xxx`
	- `/settings provider=qwen|openai|deepseek|mock`
	- `/settings model=<model-name>`
	- `/settings enable_search=true|false`

开启联网搜索后，模型客户端在构建请求 payload 时会注入 `enable_search`，并在支持的提供商（DeepSeek / Qwen）上触发网络检索。

---

## 测试与开发

- 项目包含 `_full_test.py`（全面自测脚本），可在项目根运行：

```powershell
python _full_test.py
```

- 本地开发建议使用 `mock` 模式：无需 API Key，所有功能可在本地回放与测试。

---

## 贡献与扩展

- 增加模型：继承 `BaseModelClient` 并实现 `generate_step`。
- 增加工具：实现继承自 `BaseTool` 的类，使用 `@tool_plugin` 注册。
- 增加适配器：在 `src/clawmini/adapters/` 中加入新的 Gateway 或第三方集成。

感谢使用 Clawmini！如需我把 README 同步到仓库内其它 README 文件（src 下各模块 README），我会一并更新。
