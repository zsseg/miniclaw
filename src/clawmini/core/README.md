# core 核心编排层

core 目录负责智能体主流程编排：配置装配、意图识别、ReAct 迭代、记忆与安全控制。

## 目录职责

- agent.py：主入口，构造 ClawminiAgent，注册模型客户端与工具，处理用户请求。
- react_loop.py：执行 Thought -> Action -> Observation 循环，管理轮数、轨迹与终止条件。
- memory.py：会话内消息历史管理，与持久化层协作。
- security.py：路径校验、注入拦截、危险操作前置过滤。

## 关键调用链

1. GUI 或 CLI 输入进入 ClawminiAgent.handle_user_input_verbose()。
2. agent.py 执行意图识别（关键词 -> 启发式 -> API 兜底）。
3. 若需工具调用，进入 ReactLoop.run()。
4. ReactLoop 解析模型步进输出并执行 ToolRegistry.execute()。
5. Observation 回写模型，迭代直到 final_answer 或达到上限。
6. 结果写入 memory 并可落盘到 storage/history_store.py。

## 近期实现要点

- 意图识别升级为三级策略：
	- 关键词快速判定；
	- 启发式判定（祈使句 + 动作动词）；
	- API 分类兜底。
- ReAct 优先级修正：当响应同时包含 action 与 final_answer 时，优先执行 action，避免工具调用被提前截断。
- 配置联动：支持 enable_search，并在模型层请求 payload 中透传。

## 与 GUI 的对接

- app.py 的 on_send() 触发异步任务。
- _run_async() 将任务交给后台线程执行。
- _worker() 调用 handle_user_input_verbose() 并将 trace/final 写入 response_queue。
- 主线程消费 response_queue 更新界面，避免 Tkinter 卡顿。

## 调试建议

- 先用 mock provider 跑通全链路，再切换真实 API。
- 打开 verbose trace，观察每轮 Thought/Action/Observation。
- 对于“能回答但不执行工具”的问题，优先检查 react_loop.py 的步进解析与终止逻辑。

## 扩展指南

- 新增意图策略：在 agent.py 中扩展判定函数并保持短路顺序。
- 新增执行策略：在 react_loop.py 中调整终止条件或事件回调。
- 新增安全规则：在 security.py 增加独立校验函数并在工具执行前统一调用。
