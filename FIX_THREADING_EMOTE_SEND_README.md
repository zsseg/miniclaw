# 修复 threading 缺失 + 表情发送速度/日志占位

## 你这段日志里的情况

表情复读其实已经触发了：

```text
[QQEmote] ... exact=2/1 burst=2/1 -> 触发：多人/多次复读同一个表情，跟同款
```

UI 里的：

```text
[已跟发表情] [动画表情]
```

是程序内部日志占位，不一定是群里实际发出去的文字。群里如果显示的是表情，就是正常的；如果群里也显示这串文字，那才是发送通道走错。

真正的错误是：

```text
[QQVision] 启动识图线程失败 ... name 'threading' is not defined
```

说明代码用了 `threading.Thread(...)`，但文件顶部没有 `import threading`。

## 这版修什么

1. 补 `import threading`。
2. 图片表情发送优先用 CQ `file` 字段，失败再回退 URL，通常比直接 URL 更快。
3. UI 日志里的表情占位改成 `[已发送一个表情]`，避免误会成群里发了文字。

## 使用

```powershell
cd E:\MiniClaw\miniclaw

python .\fix_threading_emote_send_fix.py

python -m py_compile .\src\clawmini\tools\qq_auto_reply.py

python app.py
```

## 回滚

```powershell
copy .\src\clawmini\tools\qq_auto_reply.py.bak_threading_emote_send_fix .\src\clawmini\tools\qq_auto_reply.py
```
