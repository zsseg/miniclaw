# 增强 QQVision 可见日志

## 你现在的问题

日志只显示：

```text
纯图片/表情包：已记录为背景并预热识图，不主动回复。
```

但看不到 OCR 到底有没有启动、有没有完成、有没有提取文字。

## 修复

之后应该能看到：

```text
[QQVision] 已加入识图队列 group/597912657 user/480717696 image#1: ...
[QQVision] 识图完成 group/597912657 user/480717696 image#1: 文字=你猪头吧 | 清晰度=高 | 内容=...
```

如果没有配置 key：

```text
[QQVision] 未设置 DASHSCOPE_API_KEY，识图/OCR 不会运行
```

如果识别失败：

```text
[QQVision] 识图完成 group/... image#1: 摘要=第1张图片识别失败：...
```

## 使用

```powershell
cd E:\MiniClaw\miniclaw

python .\fix_vision_visible_debug.py

python -m py_compile .\src\clawmini\tools\qq_auto_reply.py

python app.py
```

## 回滚

```powershell
copy .\src\clawmini\tools\qq_auto_reply.py.bak_vision_visible_debug .\src\clawmini\tools\qq_auto_reply.py
```
