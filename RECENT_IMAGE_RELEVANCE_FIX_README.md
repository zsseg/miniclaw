# 最近图片问答与重复回复修复

解决这个场景：

```text
A: [图片/表情包]
A: @机器人 这个图是什么意思
机器人回复1：针对图片回答
机器人回复2：图在哪里呀
```

原因是第二条 @ 消息本身没有 `image_refs`，机器人没把上一张图片关联进来；同时第一张图还在合并队列里，可能触发另一条回复。

## 使用

```powershell
cd E:\MiniClaw\miniclaw

python .\apply_recent_image_relevance_fix.py

python -m py_compile .\src\clawmini\tools\qq_auto_reply.py

python app.py
```

## 回滚

```powershell
copy .\src\clawmini\tools\qq_auto_reply.py.bak_recent_image_relevance .\src\clawmini\tools\qq_auto_reply.py
```
