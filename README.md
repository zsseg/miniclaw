# Clawmini 智能体架构

Clawmini 是一个面向课程作业的迷你智能体框架，实现了：

- 多模型接入（OpenAI / DeepSeek / Mock）
- ReAct 推理循环（Thought → Action → Observation）
- 工具调用与插件注册机制
- 本地安全隔离（路径白名单、扩展名限制、异常兜底）
- 三大业务工具：QQ 自动回复、自动撰写文稿、批量图片处理
- 扩展能力：
	- 文稿按段落编辑预览、批量生成任务与进度查询
	- 3.2 开放式写作请求支持先输出 2-3 种方案
	- QQ 网关 `mock/windows` 可切换（Windows 初始化失败自动回退）
	- 工具插件化加载（装饰器 + JSON 配置）
	- ReAct 多轮规划展示与流式输出开关
	- 安全 Shell 沙箱工具（白名单 + 参数校验）
	- 主 Agent + 文件分析子 Agent 协作雏形

## 快速开始

1. 安装依赖
2. 运行 `python -m clawmini.main`
3. 默认使用 `mock` 模型，无需密钥

## 调试入口

- 通用 CLI：`python -m clawmini.main`
- 3.2 写作调试：`python -m clawmini.debug_writing`
	- `plan <开放式请求>`：输出 2-3 方案
	- `create <主题>`：直接生成文稿
- 可视化 APP（本目录）：`python app.py`
	- 左侧聊天区：与智能体对话
	- 右侧规划轨迹：查看 Thought/Action/Observation
	- 右侧方案选择（卡片化）：对 3.2 开放式请求生成并选择方案后直接落地文稿
	- 文稿预览面板：生成后自动加载文件内容，可刷新查看

## 详细文档

- 使用文档（仿 prompt 结构）：`APP_使用文档_增强版.md`

## 目录说明

- `src/clawmini/`：核心代码
- `tests/`：单元测试

详细模块文档见各目录下 `README.md`。
