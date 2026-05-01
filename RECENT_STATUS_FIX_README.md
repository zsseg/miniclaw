# Recent Status 修复脚本

## 使用

把 `apply_recent_status_fix.py` 放到项目根目录：

```text
E:\\MiniClaw\\miniclaw\\
```

执行：

```powershell
cd E:\\MiniClaw\\miniclaw

python .\\apply_recent_status_fix.py

python -m py_compile .\\src\\clawmini\\workspace_app.py

python app.py
```

## 回滚

```powershell
copy .\\src\\clawmini\\workspace_app.py.bak_recent_status .\\src\\clawmini\\workspace_app.py
```
