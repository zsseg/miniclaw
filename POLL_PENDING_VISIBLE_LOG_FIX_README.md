# 修复主动回复不进 Live Ledger 日志

## 问题

`poll_pending` 触发的主动回复/候选回复不是从 webhook 事件回来的，
所以 `_on_qq_event_result()` 不会处理它的 `meta.reply`。

原来 `_poll_pending_private()` 只更新 Recent Status，没有把 poll_pending 里的回复追加到 Live Ledger。

## 修复

1. `qq_auto_reply.py`
   - `_poll_pending()` 发送成功后，继续写 `qq_auto_reply.log`
   - 额外返回 `meta["sent_replies"]`

2. `workspace_app.py`
   - `_poll_pending_private()` 读取 `meta["sent_replies"]`
   - 把主动回复显示到 Live Ledger
   - 同时追加系统记录：主动回复已记录

## 使用

```powershell
cd E:\MiniClaw\miniclaw

python .\apply_poll_pending_visible_log_fix.py

python -m py_compile .\src\clawmini\tools\qq_auto_reply.py
python -m py_compile .\src\clawmini\workspace_app.py

python app.py
```

## 回滚

```powershell
copy .\src\clawmini\tools\qq_auto_reply.py.bak_poll_pending_log_meta .\src\clawmini\tools\qq_auto_reply.py
copy .\src\clawmini\workspace_app.py.bak_poll_pending_visible_log .\src\clawmini\workspace_app.py
```
