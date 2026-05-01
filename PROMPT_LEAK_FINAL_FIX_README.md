# prompt 泄漏最终修复

你日志里这句是关键：

```text
[你现在的人设是 ...] 收到：[CQ:image,...]。建议你先确认需求细节，我可以继续协助。
```

这说明：
1. Qwen-VL 识图不是主要问题；
2. DeepSeek 400 后走了旧的本地兜底；
3. 旧兜底把 `custom_prompt` 拼进了回复；
4. `_send_via_gateway()` 没有做最终过滤，所以直接发群。

本脚本会同时修 5 处：

- `_build_user_content()`：图片管线只保留干净图片事实，不再把“请基于图片回复”塞进去
- `_sanitize_reply_before_send()`：重写中文过滤器
- `_send_via_gateway()`：所有发出去的文本强制过滤
- 旧 fallback：废掉 `prompt_tag = [custom_prompt]`
- 日志/ToolResult：`sent_parts` 也尽量用过滤后的文本

## 使用

把 `apply_prompt_leak_final_fix.py` 放到项目根目录：

```text
E:\MiniClaw\miniclaw\
```

执行：

```powershell
cd E:\MiniClaw\miniclaw

python .\apply_prompt_leak_final_fix.py

python -m py_compile .\src\clawmini\tools\qq_auto_reply.py

python app.py
```

## 回滚

```powershell
copy .\src\clawmini\tools\qq_auto_reply.py.bak_prompt_leak_final .\src\clawmini\tools\qq_auto_reply.py
```
