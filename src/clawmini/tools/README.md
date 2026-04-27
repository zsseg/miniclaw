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
