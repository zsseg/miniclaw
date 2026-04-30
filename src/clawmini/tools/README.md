# `tools` 工具层

本目录实现 Function Calling 的执行端。

## 已实现工具

1. `qq_auto_reply.py`
   - 功能：群聊@触发、私聊超时触发、频率控制、安静模式、日志记录
   - 扩展：支持 `set_gateway` 在 `mock/windows` 网关间切换（Windows 失败自动回退）
   - 安全：消息注入过滤、发送者匿名化

2. `writing_tool.py`
   - 功能：文稿创建、全文修改预览（diff）、按段落预览修改、提交、撤销
   - 队列：支持 `create_batch` 批量生成与 `batch_status` 进度查询
   - 安全：路径白名单、扩展名限制（仅 `.md/.txt`）、长度限制

3. `image_batch_tool.py`
   - 功能：批量缩放、格式转换、重命名、报告输出、可取消
   - 安全：空间预估、同名覆盖策略、异常隔离

4. `registry.py`
   - 统一工具注册与执行异常兜底
   - 支持装饰器插件注册（`@tool_plugin`）与 JSON 配置动态加载

5. `shell_tool.py`
   - 功能：受限执行白名单命令
   - 安全：命令白名单、参数危险字符拦截、工作目录沙箱、超时控制

## 使用方式

- 工具由 `ToolRegistry` 注册
- 模型返回 `ToolCall` 后由注册中心执行
- 执行结果进入 Observation 回传模型
- 可通过 `workspace/tools_plugins.json` 动态加载插件工具（无需修改核心代码）

### 常用命令示例（参数键）

- `writing_tool:create_batch`
   - `topics`: 主题列表
   - `output_dir`: 输出目录
   - `ext`: `.md` 或 `.txt`

- `writing_tool:preview_edit_section`
   - `file_path`: 文件路径
   - `section_index`: 段落编号（从 1 开始）
   - `instruction`: 修改指令

- `qq_auto_reply:set_gateway`
   - `mode`: `mock` / `windows`

## qq_auto_reply 详细说明

`qq_auto_reply.py` 提供 QQ 消息自动填充与自动回复能力，常见用例：

- 群聊 @ 某人 时由 AI 生成回复并通过一键填充发送；
- 私聊超时自动回复；
- 基于规则或模型生成模板并批量发送。

运行模式：

- `mock`：仅生成内容并写入日志，不与真实客户端交互（便于调试）；
- `windows`：尝试使用 Windows 自动化或 NapCat 将文本填入目标窗口并触发发送；
- `managed`：保留给将来扩展的托管网关（例如企业 QQ API）。

关键函数与参数：

- `set_gateway(mode='mock'|'windows'|'managed')`：切换发送网关；
- `handle_incoming_message(qq_message)`：处理收到的消息并根据策略决定是否回复；
- `auto_fill_and_send(text, target_window_info)`：在 `windows` 模式下执行填充与发送操作。

故障排查步骤：

1. 日志优先：查看 `workspace/qq_auto_reply.log`，里面会记录网关初始化、回退和错误堆栈；
2. 模式验证：在设置界面或命令行运行 `qq_auto_reply:set_gateway mode=mock` 以确认消息生成逻辑正确；
3. NapCat/自动化：若使用 `windows` 模式，确认 NapCat 或相应自动化工具已经安装并有权限访问目标窗口；
4. 权限问题：在 Windows 上自动化可能需管理员权限，尝试以管理员身份运行程序进行验证；
5. 回退机制：若 `windows` 网关初始化失败，工具会自动回退到 `mock` 模式并写入日志，检查回退原因并修复依赖或权限问题；

调试建议：

- 在 `mock` 模式下记录 `auto_fill_and_send` 的 `text` 与 `target_window_info`，用于本地复现；
- 在 `windows` 模式下，可先手动打开目标聊天窗口并确保窗口可见，再触发自动填充；
- 如需自动化脚本级别排查，建议编写小脚本调用 `qq_auto_reply.auto_fill_and_send()` 并打印返回值与异常堆栈。

安全与隐私：

- 自动发送功能需谨慎开启，建议在企业或测试账户下先行验证；
- 工具在发送前会对敏感信息进行基本过滤与脱敏（可配置）。
