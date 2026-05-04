# 表情包复读 + 回复时偶尔发群友表情包

## 功能 1：表情包/QQ 表情复读

支持：

- `[CQ:face,id=...]`
- `[CQ:image,...]`，包括动画表情、表情包图片

规则：

- 多人复读同一个表情 / 表情包时，bot 偶尔跟一次；
- 同群同一个表情有冷却，默认 75 秒；
- 不走大模型，直接用 OneBot 消息段发送；
- 不发送 raw CQ 源码，所以不会显示 `[CQ:image,...]` 这种代码。

可调：

```powershell
$env:QQ_EMOTE_REPEAT_COOLDOWN_SEC="75"
```

## 功能 2：回复时偶尔带一个群友发过的表情包

bot 会收集群友发过的 QQ face / image 表情，保存到：

```text
qq_emote_pool.json
```

普通群聊文本回复成功后，按概率额外发一个表情：

```powershell
$env:QQ_REPLY_EMOTE_PROB="0.12"
$env:QQ_REPLY_EMOTE_COOLDOWN_SEC="100"
```

默认 12% 概率，且同群至少间隔 100 秒，避免刷屏。

## 表情池参数

```powershell
$env:QQ_EMOTE_POOL_MAX="120"
$env:QQ_EMOTE_POOL_TTL_HOURS="24"
```

注意：图片表情通常依赖 QQ 临时 URL/rkey，太久可能失效，所以默认只保留 24 小时。`CQ:face` 这种 QQ 内置表情不受这个影响。

## 使用

```powershell
cd E:\MiniClaw\miniclaw

python .\apply_emote_repeat_and_pool.py

python -m py_compile .\src\clawmini\tools\qq_auto_reply.py

python app.py
```

## 回滚

```powershell
copy .\src\clawmini\tools\qq_auto_reply.py.bak_emote_repeat_pool .\src\clawmini\tools\qq_auto_reply.py
```
