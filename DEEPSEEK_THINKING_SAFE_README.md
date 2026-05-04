# 安全启用 DeepSeek Thinking

上一个脚本失败的原因：
它把 `payload = self._prepare_deepseek_payload(...)` 插到了多行 `urllib.request.Request(...)` 的参数里面，所以产生 SyntaxError。

这个脚本改用 AST：
- 找到包含 `json.dumps(payload)` 的完整语句；
- 插到完整语句前；
- 只 patch 主回复 DeepSeek 请求；
- 不 patch Qwen-VL 识图请求，也不 patch NapCat get_msg 请求。

## 使用

把 `apply_deepseek_thinking_safe.py` 放到项目根目录：

```text
E:\MiniClaw\miniclaw\
```

执行：

```powershell
cd E:\MiniClaw\miniclaw

python .\apply_deepseek_thinking_safe.py

python -m py_compile .\src\clawmini\tools\qq_auto_reply.py

python app.py
```

## 回滚

```powershell
copy .\src\clawmini\tools\qq_auto_reply.py.bak_deepseek_thinking_safe .\src\clawmini\tools\qq_auto_reply.py
```
