# 群聊回复相关度与频率优化

## 改动

1. 图片不再必回，纳入自动回复频率限制。
2. 更常回复：
   - @ 机器人
   - 回复机器人上一条
   - 点名 wick / Redamancy / 机器人 / bot / 猫娘
   - “你觉得 / 你看 / 帮我 / 看看 / 这图啥意思”
3. 更少回复：
   - 普通群友之间闲聊
   - 纯表情包
   - 没人问机器人的普通图片
4. 合并队列不再因为无关消息攒够条数就强行回复。

## 使用

```powershell
cd E:\MiniClaw\miniclaw

python .\apply_group_relevance_frequency_fix.py

python -m py_compile .\src\clawmini\tools\qq_auto_reply.py

python app.py
```

## 回滚

```powershell
copy .\src\clawmini\tools\qq_auto_reply.py.bak_relevance_frequency .\src\clawmini\tools\qq_auto_reply.py
```
