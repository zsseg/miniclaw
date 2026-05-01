# 顶部胶囊按钮 + 可编辑状态卡补丁

这版解决：

1. 顶部三个按钮太丑  
   → 改成胶囊工具组：启动 / 保存配置 / 状态。

2. 自动回复页四个框没意义  
   → 四个框全部改成可编辑卡：
   - Auto Reply：启用、私聊、识图、延时、冷却
   - Model：Provider、Model
   - Gateway：网关、NapCat API、托管账号
   - Target Groups：目标群号、机器人 ID

3. 群号显示不完整  
   → 群号卡改成直接绑定 `qq_group_var` 的输入框。长群号/多群号可以直接编辑。

每张卡片都有“保存”，会调用原来的 `on_qq_configure()` 写回配置。

## 使用

把 `apply_editable_cards_ui.py` 放到项目根目录：

```text
E:\MiniClaw\miniclaw\
```

然后执行：

```powershell
cd E:\MiniClaw\miniclaw

python .\apply_editable_cards_ui.py

python -m py_compile .\src\clawmini\ui_theme.py
python -m py_compile .\src\clawmini\workspace_app.py

python app.py
```

## 回滚

```powershell
copy .\src\clawmini\workspace_app.py.bak_card_editable .\src\clawmini\workspace_app.py
copy .\src\clawmini\ui_theme.py.bak_card_editable .\src\clawmini\ui_theme.py
```
