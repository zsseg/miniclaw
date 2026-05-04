# 启用 DeepSeek Thinking 模式

你的诊断结果说明：

```text
thinking={"type":"disabled"} + reasoning_effort="high" 会 400
```

要启用思考，应改成：

```json
"thinking": {"type": "enabled"},
"reasoning_effort": "high"
```

## 使用

把 `apply_deepseek_thinking_enabled.py` 放到项目根目录：

```text
E:\MiniClaw\miniclaw\
```

执行：

```powershell
cd E:\MiniClaw\miniclaw

python .\apply_deepseek_thinking_enabled.py

python -m py_compile .\src\clawmini\tools\qq_auto_reply.py

python app.py
```

## 回滚

```powershell
copy .\src\clawmini\tools\qq_auto_reply.py.bak_deepseek_thinking_enabled .\src\clawmini\tools\qq_auto_reply.py
```

## 想开 Max

脚本默认是：

```python
payload["reasoning_effort"] = "high"
```

如果要最强思考，把补丁后的 `qq_auto_reply.py` 里这行改成：

```python
payload["reasoning_effort"] = "max"
```
