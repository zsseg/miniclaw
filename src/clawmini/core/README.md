# `core` 核心编排层

`core` 目录负责“智能体如何运转”。

## 模块职责

- `agent.py`：系统装配入口，初始化模型、工具、存储与 ReAct 循环。
- `memory.py`：维护多轮消息历史。
- `react_loop.py`：执行 Thought → Action → Observation 迭代。
- `security.py`：路径白名单、注入过滤等安全能力。

## 使用示例

1. 构造 `AgentConfig`
2. 初始化 `ClawminiAgent`
3. 调用 `handle_user_input()`

## 设计要点

- **安全优先**：先过滤/校验，再执行工具。
- **可扩展**：模型与工具均为可插拔。
- **可观察**：每轮 Thought/Observation 都进入历史记录。

## 2.2 扩展建议落地

- 对话历史持久化：`storage/history_store.py` 已实现 JSON 落盘与恢复。
- 多轮规划展示：`react_loop.py` 提供 `traces` 与事件回调，CLI 可显示每轮轨迹。
- 流式输出：`main.py` 支持 `/stream on|off` 逐字输出。
- 多 Agent 协作：`sub_agents.py` 提供文件分析子 Agent，由主 Agent 委托。
