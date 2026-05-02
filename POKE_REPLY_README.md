# 添加戳一戳回应

## 修复点

现在 `_handle_gateway_event()` 会把 `post_type=notice` 的非消息事件全部忽略，所以戳一戳不会触发任何回复。

这个补丁会在“忽略非消息事件”之前先识别戳一戳：

```text
post_type=notice
notice_type=notify
sub_type=poke
```

## 行为

- 只回应戳自己的事件；
- 群聊只在目标群里回应；
- 私聊需要私聊自动回复开启；
- 有独立冷却：
  - 同群 5 秒
  - 同用户 18 秒
- 回复是短句，不走大模型，避免戳一下还等 API。

## 使用

```powershell
cd E:\MiniClaw\miniclaw

python .\apply_poke_reply.py

python -m py_compile .\src\clawmini\tools\qq_auto_reply.py

python app.py
```

## 回滚

```powershell
copy .\src\clawmini\tools\qq_auto_reply.py.bak_poke_reply .\src\clawmini\tools\qq_auto_reply.py
```
