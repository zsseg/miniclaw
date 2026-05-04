# @ 别人时默认不回复

## 解决的问题

例如：

```text
@小小豆 讲讲你的四种模式
```

这句话是在找小小豆，不是在找 wick。即使里面有“模式”，wick 也不应该抢答。

## 新规则

- @ 自己：正常高优先级回复
- @ 别人：默认不回复，只记录背景
- @ 别人但明确提到 wick / Redamancy / 自己：允许回复

## 使用

```powershell
cd E:\MiniClaw\miniclaw

python .\apply_ignore_at_others.py

python -m py_compile .\src\clawmini\tools\qq_auto_reply.py

python app.py
```

## 回滚

```powershell
copy .\src\clawmini\tools\qq_auto_reply.py.bak_ignore_at_others .\src\clawmini\tools\qq_auto_reply.py
```
