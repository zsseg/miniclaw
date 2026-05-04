# DeepSeek Thinking payload 最终修复

这版会在所有 `json.dumps(payload...)` 前插入：

```python
payload = self._prepare_deepseek_payload(payload, endpoint)
```

它只会对 DeepSeek 主请求生效，不会影响 DashScope / Qwen-VL 识图请求。

DeepSeek 主请求会被整理为：

```python
payload["thinking"] = {"type": "enabled"}
payload["reasoning_effort"] = "high"
```

同时：
- 把 list content 转成文本，避免 DeepSeek 收到 vision 格式；
- 移除 temperature/top_p/presence_penalty/frequency_penalty/enable_search；
- max_tokens 至少 500。

## 使用

把 `apply_deepseek_thinking_payload_final.py` 放到项目根目录：

```text
E:\MiniClaw\miniclaw\
```

执行：

```powershell
cd E:\MiniClaw\miniclaw

python .\apply_deepseek_thinking_payload_final.py

python -m py_compile .\src\clawmini\tools\qq_auto_reply.py

python app.py
```

## 回滚

```powershell
copy .\src\clawmini\tools\qq_auto_reply.py.bak_thinking_payload_final .\src\clawmini\tools\qq_auto_reply.py
```
