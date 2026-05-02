# 安全恢复操作指引

修复：

```text
NameError: name 'body' is not defined
```

原因：当前 UI 是 LoveLedger/卡片式布局，`QQAutoReplyPanel._build_ui()` 里不一定有 `body`，上一个脚本把帮助信息插到了不存在的 `body` 上。

## 使用

把 `fix_restore_guide_safe.py` 放到项目根目录：

```text
E:\MiniClaw\miniclaw\
```

执行：

```powershell
cd E:\MiniClaw\miniclaw

python .\fix_restore_guide_safe.py

python -m py_compile .\src\clawmini\workspace_app.py

python app.py
```

## 回滚

```powershell
copy .\src\clawmini\workspace_app.py.bak_restore_guide_safe .\src\clawmini\workspace_app.py
```
