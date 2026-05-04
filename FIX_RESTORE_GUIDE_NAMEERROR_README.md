# 修复操作指引 NameError

错误：

```text
NameError: name 'body' is not defined
```

原因是上一个脚本把：

```python
guide = ttk.LabelFrame(body, text="操作指引", ...)
```

插到了 `body = ...` 创建之前。

## 使用

把 `fix_restore_guide_nameerror.py` 放到项目根目录：

```text
E:\MiniClaw\miniclaw\
```

执行：

```powershell
cd E:\MiniClaw\miniclaw

python .\fix_restore_guide_nameerror.py

python -m py_compile .\src\clawmini\workspace_app.py

python app.py
```

## 回滚

```powershell
copy .\src\clawmini\workspace_app.py.bak_restore_guide_nameerror .\src\clawmini\workspace_app.py
```
