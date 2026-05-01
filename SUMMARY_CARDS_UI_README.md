# 摘要卡 + 折叠编辑区 UI 补丁

这版不是把卡片改成密密麻麻的表单，而是：

- 默认展示好看的摘要卡
- 点“编辑”才展开轻量编辑区
- 保存后自动收起并刷新摘要
- 群号摘要显示“共几个群 + 前几个群号”，不再截断成没意义的一小段
- 顶部三个按钮改成胶囊工具组

## 使用

把 `apply_summary_cards_ui.py` 放到项目根目录：

```text
E:\MiniClaw\miniclaw\
```

执行：

```powershell
cd E:\MiniClaw\miniclaw

python .\apply_summary_cards_ui.py

python -m py_compile .\src\clawmini\ui_theme.py
python -m py_compile .\src\clawmini\workspace_app.py

python app.py
```

## 回滚

```powershell
copy .\src\clawmini\workspace_app.py.bak_summary_cards .\src\clawmini\workspace_app.py
copy .\src\clawmini\ui_theme.py.bak_summary_cards .\src\clawmini\ui_theme.py
```
