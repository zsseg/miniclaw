# 恢复第一版“操作指引”帮助信息

这个脚本会把 QQ 自动回复页最开始那版的帮助说明加回来：

```text
1. 先选网关：测试选 mock，正式用 managed。
2. 下载安装 NapCat：点下方「下载NapCat」按钮从官网获取。
3. 安装后点「一键启动/填充」，自动识别账号和地址。
4. 再点「更新配置」保存群号、延时等设置。
5. 先用「模拟收到消息」测试回复效果，再切换到真实 QQ。
6. 如果提示缺少 pywinauto，在终端执行：python -m pip install pywinauto
```

## 使用

把 `apply_restore_guide_info.py` 放到项目根目录：

```text
E:\MiniClaw\miniclaw\
```

执行：

```powershell
cd E:\MiniClaw\miniclaw

python .\apply_restore_guide_info.py

python -m py_compile .\src\clawmini\workspace_app.py

python app.py
```

## 回滚

```powershell
copy .\src\clawmini\workspace_app.py.bak_restore_guide .\src\clawmini\workspace_app.py
```
