# 动态人格社交判断版

## 解决的问题

上一个版本把“有自己的想法”写成了固定词表，例如 OC / bug / 模式 / 人设。
这会显得很死。

这个版本改成：

- 不在代码里写死 wick 喜欢什么
- 让模型从 custom_prompt 和最近聊天里自己推断 wick 的偏好、雷点、好奇点
- 非 @ 消息先走一个“社交判断 gate”
- gate 判断 wick 是否真的有想法、是否适合冒泡
- 只有 gate 认为自然时，才主动回复或进入候选队列

## 代价

非 @ 的普通群消息会多一次小请求，用来判断要不要说话。
这样比固定关键词更像真人，但会增加一点延迟和费用。

## 使用

```powershell
cd E:\MiniClaw\miniclaw

python .\apply_dynamic_personality_gate.py

python -m py_compile .\src\clawmini\tools\qq_auto_reply.py

python app.py
```

## 回滚

```powershell
copy .\src\clawmini\tools\qq_auto_reply.py.bak_dynamic_personality_gate .\src\clawmini\tools\qq_auto_reply.py
```
