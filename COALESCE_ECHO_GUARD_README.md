# 修复主动回复刷屏和复读循环

## 日志里看到的问题

1. 短时间内多条非 @ 消息分别触发回复，导致刷屏。
2. 群友复读 bot 刚说过的话，bot 又继续接，形成复制粘贴循环。
3. 单条主动候选有时被等没了；多条候选又容易变成多条回复。

## 修复

- @ 自己 / 回复自己：仍然立即回复。
- 非 @ 的主动回复：先进候选队列，由 poll_pending 合并成一条。
- 候选等待时间收敛到 8~14 秒。
- 单条高置信候选到期也能发。
- 识别群友复读 bot 最近回复，只记录不继续接。
- 候选队列里去重重复内容。

## 使用

```powershell
cd E:\MiniClaw\miniclaw

python .\apply_coalesce_echo_guard.py

python -m py_compile .\src\clawmini\tools\qq_auto_reply.py

python app.py
```

## 回滚

```powershell
copy .\src\clawmini\tools\qq_auto_reply.py.bak_coalesce_echo_guard .\src\clawmini\tools\qq_auto_reply.py
```
