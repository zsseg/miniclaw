# 修复 DeepSeek unknown variant image_url

错误：

```text
messages[1]: unknown variant `image_url`, expected `text`
```

说明 DeepSeek 收到了图片格式的 `content` list。DeepSeek 这里只能收文本，所以要在 `_generate_reply_via_api` 发请求前把 `image_url` 转成 `[图片]` 或图片描述文本。

## 使用

```powershell
cd E:\MiniClaw\miniclaw

python .\apply_deepseek_image_url_400_fix.py

python -m py_compile .\src\clawmini\tools\qq_auto_reply.py

python app.py
```

## 回滚

```powershell
copy .\src\clawmini\tools\qq_auto_reply.py.bak_deepseek_image_url_400_fix .\src\clawmini\tools\qq_auto_reply.py
```
