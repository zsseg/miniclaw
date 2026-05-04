# 彻底修复识图 prompt 泄漏

这版修的是根因：

`_build_user_content()` 原来会返回：

```text
〖图片内容解析，来自 Qwen-VL〗
- 第1张图片：...
请基于上面的图片内容，用自然 QQ 聊天语气回复。
```

如果 DeepSeek 400 或兜底逻辑回显输入，就会把这一整段 prompt 发进群。

现在改成只返回：

```text
用户原文

图片内容：
- 第1张图片：...
```

并且发送前强制过滤所有 prompt。

## 使用

把 `apply_image_prompt_pipeline_fix.py` 放到项目根目录：

```text
E:\MiniClaw\miniclaw\
```

执行：

```powershell
cd E:\MiniClaw\miniclaw

python .\apply_image_prompt_pipeline_fix.py

python -m py_compile .\src\clawmini\tools\qq_auto_reply.py

python app.py
```

## 回滚

```powershell
copy .\src\clawmini\tools\qq_auto_reply.py.bak_image_prompt_pipeline_fix .\src\clawmini\tools\qq_auto_reply.py
```
