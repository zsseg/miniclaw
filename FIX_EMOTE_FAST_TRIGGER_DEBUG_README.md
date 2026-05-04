# 修复表情包复读不触发 + 增加 QQEmote 调试日志

## 为什么之前可能没触发

常见原因有几个：

1. fast path 可能插在“纯图片/表情包直接 return”后面，所以根本没跑到表情复读判断。
2. 目标群判断可能是 `str` 和 `int` 不匹配，例如 `597912657` vs `"597912657"`。
3. 上一版默认要求多人参与，同一个人连发同款表情可能不触发。
4. 条件没达到但日志没打出来，所以看不出是没记录、没达阈值、冷却中，还是发送失败。

## 这版修什么

- fast path 会尽量插在纯图/表情包硬忽略之前；
- 目标群统一转字符串判断；
- 默认更灵敏：
  - 同款表情 2 次即可触发；
  - 不完全相同的表情流默认 3 条即可触发；
  - 默认不再强制要求 2 个不同用户；
- 每条纯表情/表情包都会输出 `[QQEmote]` 日志。

示例日志：

```text
[QQEmote] group/597912657 user/480717696: pure=True items=1 exact=1/1 burst=1/1 -> 不触发：未达阈值 exact=1/1 需要>=2/1; burst=1/1 需要>=3/1
```

触发时：

```text
[QQEmote] group/597912657 user/480717696: pure=True items=1 exact=2/1 burst=2/1 -> 触发：多人/多次复读同一个表情，跟同款
```

## 使用

```powershell
cd E:\MiniClaw\miniclaw

python .\fix_emote_fast_trigger_debug.py

python -m py_compile .\src\clawmini\tools\qq_auto_reply.py

python app.py
```

## 可调参数

```powershell
$env:QQ_EMOTE_DEBUG="1"
$env:QQ_EMOTE_EXACT_REPEAT_MIN_COUNT="2"
$env:QQ_EMOTE_EXACT_REPEAT_MIN_USERS="1"
$env:QQ_EMOTE_BURST_MIN_COUNT="3"
$env:QQ_EMOTE_BURST_MIN_USERS="1"
$env:QQ_EMOTE_FAST_GROUP_COOLDOWN_SEC="6"
```

想让不同表情包刷屏更容易触发：

```powershell
$env:QQ_EMOTE_BURST_MIN_COUNT="2"
```

想要求至少两个人参与才跟：

```powershell
$env:QQ_EMOTE_EXACT_REPEAT_MIN_USERS="2"
$env:QQ_EMOTE_BURST_MIN_USERS="2"
```

## 回滚

```powershell
copy .\src\clawmini\tools\qq_auto_reply.py.bak_emote_fast_trigger_debug .\src\clawmini\tools\qq_auto_reply.py
```
