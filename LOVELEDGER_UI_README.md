# LoveLedger 整体布局改造说明

这次不是只改颜色，会把 GitHub `New_write` 分支里的 `QQAutoReplyPanel._build_ui()` 替换成参考图那种布局：

- 左侧深绿色账本导航栏
- 右侧 QQ Bot Overview 仪表盘
- 顶部操作按钮
- 4 个状态卡片
- 中间左侧大日志卡片
- 中间右侧状态/快捷操作卡片
- 底部滚动配置账本区域

## 使用

把这三个文件放到项目根目录：

```text
E:\MiniClaw\miniclaw\
```

1. 覆盖主题文件：

```powershell
copy .\src\clawmini\ui_theme.py .\src\clawmini\ui_theme.py.bak_loveledger
copy .\ui_theme_loveledger_full.py .\src\clawmini\ui_theme.py
```

2. 执行布局补丁：

```powershell
python .\apply_loveledger_layout.py
```

3. 检查语法：

```powershell
python -m py_compile .\src\clawmini\ui_theme.py
python -m py_compile .\src\clawmini\workspace_app.py
```

4. 启动：

```powershell
python app.py
```

## 回滚

```powershell
copy .\src\clawmini\workspace_app.py.bak_loveledger .\src\clawmini\workspace_app.py
copy .\src\clawmini\ui_theme.py.bak_loveledger .\src\clawmini\ui_theme.py
```
