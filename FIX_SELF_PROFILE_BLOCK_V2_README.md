# 修复 self_profile_block 未定义 v2

上一个修复脚本自身有一处 f-string 生成错误：

```text
NameError: name '_self_profile_exc' is not defined
```

这个 v2 已修复该问题。

## 使用

```powershell
cd E:\MiniClaw\miniclaw

python .\fix_self_profile_block_nameerror_v2.py

python -m py_compile .\src\clawmini\tools\qq_auto_reply.py

python app.py
```

## 回滚

```powershell
copy .\src\clawmini\tools\qq_auto_reply.py.bak_fix_self_profile_block_v2 .\src\clawmini\tools\qq_auto_reply.py
```
