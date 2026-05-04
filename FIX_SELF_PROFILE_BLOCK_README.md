# 修复 self_profile_block 未定义

## 问题

日志里出现：

```text
NameError: name 'self_profile_block' is not defined
```

这会导致真正要回复的时候直接崩掉，所以看起来像 bot 变哑巴。

## 使用

```powershell
cd E:\MiniClaw\miniclaw

python .\fix_self_profile_block_nameerror.py

python -m py_compile .\src\clawmini\tools\qq_auto_reply.py

python app.py
```

## 回滚

```powershell
copy .\src\clawmini\tools\qq_auto_reply.py.bak_fix_self_profile_block .\src\clawmini\tools\qq_auto_reply.py
```
