# UI 分组修复补丁

这版修复你指出的问题：

1. “新增群号”为啥不和“目标群号”在一起  
   → 现在底部第一个分组就是「Overview 群组 & 基础」，里面先是「当前目标群」，下面紧跟「群号管理：新增 / 删除 / 修改」。

2. “更新配置”为啥不是全局的  
   → 顶部右上角固定为「保存全部」。底部不再在模拟测试里乱放更新配置；各分组里的保存按钮也统一叫「保存全部」，都调用同一个 `on_qq_configure()`。

3. 其他顺手检查并修正：
   - 模型和联网搜索放到同一个「Advisor 模型 & 搜索」
   - NapCat 网关单独一组
   - 模拟收到消息 / 手动回复单独一组，不和群号管理混在一起
   - Quick Actions 不再重复放“查询状态”
   - 四个摘要卡保留展示态，点击编辑才展开，不再变成丑表单卡
   - 群号摘要展示“共 N 个群 + 前几个群号”，长群号不再硬截断成没意义的一小段

## 使用

把 `apply_ui_grouping_fix.py` 放到项目根目录：

```text
E:\MiniClaw\miniclaw\
```

执行：

```powershell
cd E:\MiniClaw\miniclaw

python .\apply_ui_grouping_fix.py

python -m py_compile .\src\clawmini\ui_theme.py
python -m py_compile .\src\clawmini\workspace_app.py

python app.py
```

## 回滚

```powershell
copy .\src\clawmini\workspace_app.py.bak_grouping_fix .\src\clawmini\workspace_app.py
copy .\src\clawmini\ui_theme.py.bak_grouping_fix .\src\clawmini\ui_theme.py
```
