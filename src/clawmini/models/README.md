# `models` 模型适配层

本目录负责“把统一的智能体请求发给不同大模型”。

## 模块说明

- `base.py`：抽象接口 `BaseModelClient`
- `mock_model.py`：离线规则模型，便于本地调试和测试
- `openai_model.py`：OpenAI Chat Completions 适配
- `deepseek_model.py`：DeepSeek（OpenAI 兼容）适配

## 接口契约

输入：
- `messages`：多轮对话历史
- `tool_schemas`：可调用工具定义

输出：
- `AgentStep`：包含 `thought`、`action`、`final_answer`

## 扩展方式

新增模型时：
1. 继承 `BaseModelClient`
2. 实现 `generate_step`
3. 在 `core/agent.py` 中接入配置分支
