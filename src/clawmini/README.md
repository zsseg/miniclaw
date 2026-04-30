# `src/clawmini` 模块说明

本目录实现 Clawmini 的主代码，采用“核心循环 + 模型适配 + 工具插件”的分层结构。

## 使用方式

## 子模块

- `core/`：消息循环、智能体编排、安全控制
- `adapters/`：外部系统适配层（如 QQ 客户端）
## 与 GUI 的对接（app.py）

GUI（`app.py`）通过线程与队列与核心 Agent 对接，主要交互点：

- `on_send()`：用户在输入框发送消息后调用，负责将用户消息入会话并触发 `_run_async('agent_message', payload)`；
- `_run_async()`：在后台线程调度 `agent.handle_user_input_verbose()` 并传入回调，防止阻塞主线程；
- `_worker()`：消费后台任务结果，将 `AgentStep` 轨迹与最终回答通过 `response_queue` 回写到 GUI；
- `_build_main_agent_config_from_ui()`：从设置面板读取配置（模型、API Key、enable_search、gateway 模式等），构造 `AgentConfig` 并重建 `ClawminiAgent`；

实现要点：GUI 主线程仅负责渲染与用户交互，所有模型调用和工具执行都在后台线程完成，结果再回写到主线程更新界面。这样设计可避免 Tkinter 卡住并保持响应流畅。
- `storage/`：会话与日志持久化

每个子目录包含独立 `README.md`，介绍职责与扩展方法。
