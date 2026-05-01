# 紧凑 LoveLedger UI 改造说明

这版按你的反馈重做：

- 不放大面积无用装饰栏
- 日志区保留最大可用空间
- 参数分成 4 个可用分组标签：
  - Overview 基础
  - Advisor 模型
  - Vault NapCat
  - Envelopes 群号/模拟
- 顶部三个主标签通过 `TNotebook.Tab` 美化成账本分页风格
- 整体仍然是复古账本风格，但不牺牲可用空间

## 使用

把两个文件放到项目根目录：

```text
E:\MiniClaw\miniclaw\
```

然后运行：

```powershell
cd E:\MiniClaw\miniclaw

copy .\src\clawmini\ui_theme.py .\src\clawmini\ui_theme.py.bak_compact_loveledger
copy .\ui_theme_loveledger_compact.py .\src\clawmini\ui_theme.py

python .\apply_compact_loveledger_layout.py

python -m py_compile .\src\clawmini\ui_theme.py
python -m py_compile .\src\clawmini\workspace_app.py

python app.py
```

## 回滚

```powershell
copy .\src\clawmini\workspace_app.py.bak_compact_loveledger .\src\clawmini\workspace_app.py
copy .\src\clawmini\ui_theme.py.bak_compact_loveledger .\src\clawmini\ui_theme.py
```
