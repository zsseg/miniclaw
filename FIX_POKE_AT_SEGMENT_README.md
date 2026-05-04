# 修复戳一戳 @ 显示成 CQ 源码

## 问题

之前是把：

```text
[CQ:at,qq=用户QQ] 喵？！
```

当作普通字符串交给发送网关。

如果 NapCat / 网关把字符串按纯文本发送，群里就会直接显示这串代码，而不会变成真正 @。

## 修复

这版不再用 raw CQ 字符串做 @，而是直接向 NapCat/OneBot 发送消息段：

```json
[
  {"type": "at", "data": {"qq": 用户QQ}},
  {"type": "text", "data": {"text": " 喵？！"}}
]
```

如果消息段接口失败，会退回普通文本，但不会再把 `[CQ:at,qq=...]` 发到群里。

## 使用

```powershell
cd E:\MiniClaw\miniclaw

python .\fix_poke_at_segment.py

python -m py_compile .\src\clawmini\tools\qq_auto_reply.py

python app.py
```

## 回滚

```powershell
copy .\src\clawmini\tools\qq_auto_reply.py.bak_poke_at_segment .\src\clawmini\tools\qq_auto_reply.py
```
