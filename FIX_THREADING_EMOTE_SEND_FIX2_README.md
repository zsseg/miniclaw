# 修复上一版 import threading 插入位置错误

上一版脚本在给 `qq_auto_reply.py` 补 `import threading` 时，可能把它插进了多行 import / 括号结构中，导致脚本内部 `ast.parse(src)` 报：

```text
SyntaxError: invalid syntax
import threading
```

你的 `python -m py_compile .\src\clawmini\tools\qq_auto_reply.py` 已经通过，说明目标文件本身没被写坏，脚本失败发生在写入前的临时 `src` 上。

## 这版修什么

1. 用 AST 找安全插入点，不会把 `import threading` 插进多行 import 里。
2. 图片表情发送优先用 CQ `file` 字段，失败再回退 URL。
3. UI 日志里的表情占位改成 `[已发送一个表情]`。

## 使用

```powershell
cd E:\MiniClaw\miniclaw

python .\fix_threading_emote_send_fix2.py

python -m py_compile .\src\clawmini\tools\qq_auto_reply.py

python app.py
```

## 回滚

```powershell
copy .\src\clawmini\tools\qq_auto_reply.py.bak_threading_emote_send_fix2 .\src\clawmini\tools\qq_auto_reply.py
```
