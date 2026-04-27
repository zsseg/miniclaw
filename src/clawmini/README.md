# `src/clawmini` 模块说明

本目录实现 Clawmini 的主代码，采用“核心循环 + 模型适配 + 工具插件”的分层结构。

## 使用方式

- 程序入口：`python -m clawmini.main`
- 构建智能体：`clawmini.core.agent.ClawminiAgent`
- 默认模型：`mock`（离线可运行）

## 子模块

- `core/`：消息循环、智能体编排、安全控制
- `models/`：OpenAI/DeepSeek/Mock 模型适配
- `tools/`：工具协议、注册中心、三个业务工具
- `adapters/`：外部系统适配层（如 QQ 客户端）
- `storage/`：会话与日志持久化

每个子目录包含独立 `README.md`，介绍职责与扩展方法。
