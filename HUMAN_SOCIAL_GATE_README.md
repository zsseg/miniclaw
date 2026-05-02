# 人格化社交判断版 QQ 自动回复

目标：让 bot 更像真人群友。

## 改动

1. 普通群消息只观察，不进入合并回复队列。
2. 只有相关消息才进入候选队列：
   - @ 它 / 回复它
   - 点名 wick / Redamancy / bot / 机器人 / 猫娘
   - 问它“你觉得/你看/帮我看看”
   - 讨论它的 OC / 人设 / 模式 / 回复概率 / 触发规则
   - 发图后问“这个图什么意思”
3. 纯图、纯表情、普通闲聊不会自动补发。
4. 合并队列加守门，不会到期硬插话。
5. 回复 prompt 增加“像真人群友，有想法但不暴露程序逻辑”。

## 使用

```powershell
cd E:\MiniClaw\miniclaw

python .\apply_human_social_gate.py

python -m py_compile .\src\clawmini\tools\qq_auto_reply.py

python app.py
```

## 回滚

```powershell
copy .\src\clawmini\tools\qq_auto_reply.py.bak_human_social_gate .\src\clawmini\tools\qq_auto_reply.py
```
