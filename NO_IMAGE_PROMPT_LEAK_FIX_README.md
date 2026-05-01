# 修复识图后往群里发 prompt 的问题

问题原因：
- Qwen-VL 识图是正常的；
- 但 `qq_auto_reply.py` 会把 Qwen-VL 结果和“请基于图片内容回复”这种中间提示拼成主模型输入；
- 如果主模型失败、兜底逻辑回显、或发送前没有做过滤，就可能把这段中间提示原样发进群；
- 当前 `_sanitize_reply_before_send` 里的中文关键字疑似乱码，而且 `_send_via_gateway` 没强制调用 sanitizer，所以拦不住。

## 使用

把 `apply_no_image_prompt_leak_fix.py` 放到项目根目录：

```text
E:\MiniClaw\miniclaw\
```

执行：

```powershell
cd E:\MiniClaw\miniclaw

python .\apply_no_image_prompt_leak_fix.py

python -m py_compile .\src\clawmini\tools\qq_auto_reply.py

python app.py
```

## 回滚

```powershell
copy .\src\clawmini\tools\qq_auto_reply.py.bak_no_image_prompt_leak .\src\clawmini\tools\qq_auto_reply.py
```
