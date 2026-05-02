# 修复 guide is not defined

错误：

```text
NameError: name 'guide' is not defined
```

原因：之前的脚本留下了半截操作指引代码，只剩：

```python
guide.pack(...)
```

但 `guide = ttk.LabelFrame(...)` 已经被删掉了。

## 使用

把 `fix_orphan_guide_block.py` 放到项目根目录：

```text
E:\MiniClaw\miniclaw\
```

执行：

```powershell
cd E:\MiniClaw\miniclaw

python .\fix_orphan_guide_block.py

python -m py_compile .\src\clawmini\workspace_app.py

python app.py
```

## 回滚

```powershell
copy .\src\clawmini\workspace_app.py.bak_fix_orphan_guide .\src\clawmini\workspace_app.py
```
