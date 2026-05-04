# 参与复读 + 主动开话题

## 功能 1：大家复读时参与一下

规则：

- 多人复读同一句短句时，机器人会偶尔跟一次；
- 不跟链接、命令、超长内容、纯 CQ 图片/表情；
- 不跟“群友复读 bot 刚说过的话”，避免循环；
- 同群同一句有冷却，默认 55 秒；
- 复读回复直接发送原短句，不走大模型，速度快。

可调：

```powershell
$env:QQ_REPEAT_JOIN_COOLDOWN_SEC="55"
```

## 功能 2：偶尔主动开话题

规则：

- 没有待回复内容；
- 不在普通回复冷却；
- 距离上次主动开话题/上次自动回复超过设定间隔；
- 使用当前 custom_prompt 和最近群聊生成一句自然短句；
- 不写死人设、兴趣点、名字；
- 默认开启，默认间隔 1200 秒（20 分钟）。

可调：

```powershell
$env:QQ_PROACTIVE_TOPIC_ENABLED="1"
$env:QQ_PROACTIVE_TOPIC_INTERVAL_SEC="1200"
```

建议间隔：

```text
600~900 秒：更活跃
1200~1800 秒：更像偶尔冒泡
```

## 使用

```powershell
cd E:\MiniClaw\miniclaw

python .\apply_repeat_and_proactive_topic.py

python -m py_compile .\src\clawmini\tools\qq_auto_reply.py

python app.py
```

## 回滚

```powershell
copy .\src\clawmini\tools\qq_auto_reply.py.bak_repeat_and_proactive .\src\clawmini\tools\qq_auto_reply.py
```
