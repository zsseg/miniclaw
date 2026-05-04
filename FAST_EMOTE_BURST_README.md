# 表情包复读更快 + 不完全相同表情流也能跟发

## 修复 1：复读太慢

之前表情包可能被“纯图片/表情包背景预热识图”吃掉，或者走到后面的候选/轮询逻辑，所以显得慢。

这版加了 fast path：

```text
纯表情/表情包消息进来
先记录表情流
立即判断要不要跟发
不等 OCR
不进大模型
```

## 修复 2：不完全相同表情包也能跟

现在有两种触发：

```text
1. exact repeat
   多人发同一个表情/表情包
   bot 跟同款

2. burst
   多人在短时间内发很多表情/表情包
   即使不完全相同
   bot 也从表情池里挑一个跟着发
```

## 表情选择

仍然使用 use_count 均衡：

```text
不避开最近表情
不硬排除
优先从用得少的一批里随机挑
```

## 使用

```powershell
cd E:\MiniClaw\miniclaw

python .\fix_fast_emote_burst.py

python -m py_compile .\src\clawmini\tools\qq_auto_reply.py

python app.py
```

## 可调参数

```powershell
$env:QQ_EMOTE_BURST_WINDOW_SEC="18"
$env:QQ_EMOTE_BURST_MIN_COUNT="3"
$env:QQ_EMOTE_BURST_MIN_USERS="2"
$env:QQ_EMOTE_FAST_GROUP_COOLDOWN_SEC="10"
$env:QQ_EMOTE_EXACT_REPEAT_COOLDOWN_SEC="18"
$env:QQ_EMOTE_BURST_COOLDOWN_SEC="24"
```

建议：

```text
想更灵敏：
QQ_EMOTE_BURST_MIN_COUNT=2
QQ_EMOTE_FAST_GROUP_COOLDOWN_SEC=6

想更克制：
QQ_EMOTE_BURST_MIN_COUNT=4
QQ_EMOTE_BURST_COOLDOWN_SEC=35
```

## 回滚

```powershell
copy .\src\clawmini\tools\qq_auto_reply.py.bak_fast_emote_burst .\src\clawmini\tools\qq_auto_reply.py
```
