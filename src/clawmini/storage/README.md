# `storage` 持久化层

本目录管理智能体运行过程中的本地持久化数据。

## 当前模块

- `history_store.py`：对话历史 JSON 读写。

## 数据格式

历史文件是消息数组，每条记录包含：
- `role`
- `content`
- `timestamp`

## 使用建议

- 生产环境可替换为 SQLite / PostgreSQL。
- 可增加分会话 ID，实现多任务并行历史管理。
