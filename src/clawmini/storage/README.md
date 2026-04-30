# storage 持久化层

storage 目录负责运行状态与历史记录的本地持久化，保证应用重启后可恢复。

## 当前模块

- history_store.py：会话消息的读写、加载、覆盖与异常兜底。

## 数据职责划分

- 会话历史：通常存放在 workspace/sessions/*.json。
- 应用状态：通常由 app_state.json 管理（模型配置、会话索引、UI 状态等）。
- 工具日志：如 qq_auto_reply.log 等按工具维度分离。

## 历史记录结构

单条消息建议字段：

- role：system/user/assistant/tool
- content：消息正文
- timestamp：ISO 时间戳
- meta（可选）：provider、tool_name、trace_id、latency_ms 等

示例：

```json
{
	"role": "assistant",
	"content": "已帮你创建文件 notes.txt",
	"timestamp": "2026-04-30T12:34:56Z",
	"meta": {
		"provider": "qwen",
		"tool_name": "workspace_files"
	}
}
```

## 容错与一致性建议

- 写入采用原子策略（临时文件 + 替换）避免意外中断导致损坏。
- 读取失败时返回空历史并记录错误日志，保证主流程不中断。
- 建议对超长会话进行分片或归档，避免单文件无限增长。

## 与 core 的协作

- core/memory.py 管理内存中的会话消息。
- 退出或关键节点时调用 history_store.py 落盘。
- 启动时从 storage 加载历史，恢复到 memory。

## 未来扩展

- 切换到 SQLite / PostgreSQL 获取更好的并发与检索能力。
- 增加会话级索引与标签，支持按主题/时间过滤。
- 增加审计字段（操作者、来源工具、操作摘要）便于问题回放。
