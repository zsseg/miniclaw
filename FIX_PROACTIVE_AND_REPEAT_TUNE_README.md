# 发起聊天目标/频率 + 复读阈值微调

## 修复

1. 主动开话题只发到“本轮运行中确认收到过 group 消息”的目标群。
   这样不会刚启动就往 `0`、私聊 QQ、已退群目标发。

2. 频率略降：
   ```powershell
   $env:QQ_PROACTIVE_STARTUP_GRACE_SEC="300"
   $env:QQ_PROACTIVE_GLOBAL_COOLDOWN_SEC="300"
   $env:QQ_PROACTIVE_SAME_GROUP_COOLDOWN_SEC="1800"
   ```

3. 发起聊天文本过滤：
   会丢弃“没人理我 / 群里好安静 / 数到三 / 记小本本 / 都去哪了”等不自然开场。

4. 复读阈值略降：
   ```powershell
   $env:QQ_EMOTE_BURST_MIN_COUNT="2"
   $env:QQ_EMOTE_EXACT_REPEAT_MIN_COUNT="2"
   $env:QQ_EMOTE_FAST_GROUP_COOLDOWN_SEC="5"
   ```

## 使用

```powershell
cd E:\MiniClaw\miniclaw

python .\fix_proactive_and_repeat_tune.py

python -m py_compile .\src\clawmini\tools\qq_auto_reply.py

python app.py
```

## 回滚

```powershell
copy .\src\clawmini\tools\qq_auto_reply.py.bak_proactive_and_repeat_tune .\src\clawmini\tools\qq_auto_reply.py
```
