# 最终替换 _generate_reply_via_api

这次不是插入补丁，而是直接替换整个 `_generate_reply_via_api()`。

修复目标：

```text
messages[1]: unknown variant `image_url`, expected `text`
```

DeepSeek 的 `messages[].content` 只能是字符串。这个脚本会保证 DeepSeek 分支里：

```python
{"role": "user", "content": "...纯文本..."}
```

不会再出现：

```python
{"type": "image_url", ...}
```

## 使用

```powershell
cd E:\MiniClaw\miniclaw

python .\apply_replace_generate_reply_final.py

python -m py_compile .\src\clawmini\tools\qq_auto_reply.py

python app.py
```

## 回滚

```powershell
copy .\src\clawmini\tools\qq_auto_reply.py.bak_replace_generate_reply_final .\src\clawmini\tools\qq_auto_reply.py
```
