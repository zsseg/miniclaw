# DeepSeek Thinking 精确修复

按当前 `qq_auto_reply.py` 定点修：

1. `_describe_images_with_qwen_vl` 里误加了 DeepSeek thinking 参数，Qwen-VL/DashScope 不应该带这个。
2. `_generate_reply_via_api` 里启用 DeepSeek thinking，并移除 thinking 模式下不该带的采样参数。
3. `_build_user_content` 改成只给 DeepSeek 传干净图片事实，不再传图片 prompt。
4. 如果 DeepSeek 还 400，会在 PowerShell 打出真实 body。

## 使用

```powershell
cd E:\MiniClaw\miniclaw

python .\apply_deepseek_thinking_exact_fix.py

python -m py_compile .\src\clawmini\tools\qq_auto_reply.py

python app.py
```

## 回滚

```powershell
copy .\src\clawmini\tools\qq_auto_reply.py.bak_deepseek_thinking_exact .\src\clawmini\tools\qq_auto_reply.py
```
