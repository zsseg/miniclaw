# models 模型适配层

models 目录负责将统一的 AgentStep 协议映射到不同模型提供商 API。

## 模块说明

- base.py：定义 BaseModelClient 抽象接口与通用约束。
- mock_model.py：离线规则模型，适用于单元测试和无 API Key 场景。
- openai_model.py：OpenAI 兼容客户端实现（同时服务 openai/deepseek/qwen 兼容模式）。
- deepseek_model.py：DeepSeek 便捷封装。
- qwen_model.py：Qwen 便捷封装（若仓库内启用）。

## 统一输入输出契约

输入：

- messages：对话历史（system/user/assistant/tool）。
- tool_schemas：可调用工具 JSON schema。
- runtime options：温度、最大 token、enable_search 等。

输出：

- AgentStep：
	- thought：可选思考摘要；
	- action：可选工具调用（name + parameters）；
	- final_answer：可选最终回复。

## 解析与兼容策略

- _parse_step 支持多种返回格式：
	- 标准 JSON；
	- Markdown 代码块内 JSON；
	- key:value 混合文本。
- 对“不规范输出”进行最大化容错，尽量提取 action/final_answer，降低模型漂移对执行链的影响。

## 联网搜索开关

- AgentConfig.enable_search 通过模型客户端透传到请求 payload。
- 在支持的供应商（DeepSeek/Qwen）上用于启用联网检索能力。
- 若供应商不支持，客户端应优雅降级，不影响普通对话与工具调用。

## 调试建议

- 先用 mock_model.py 验证 core 与 tool 协议。
- 真实 API 调试时打印 payload（需脱敏 api_key）与模型原始返回文本。
- 针对工具不触发问题，优先检查 _parse_step 是否成功解析 action 字段。

## 扩展新模型模板

1. 继承 BaseModelClient。
2. 实现 generate_step()，保证返回 AgentStep。
3. 复用/实现 _build_payload 与 _parse_step。
4. 在 core/agent.py 的 provider 分支接入。
5. 增加对应测试用例（正常、异常、工具调用三类）。
