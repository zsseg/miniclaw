# 修复记忆衰减过快 + 抽象接龙误触发

## 你这段日志里的问题

1. 候选半衰期太短，容易忘前面的互动。
2. “什么样的心情 / 年纪 / 欢愉 / 哭泣”这种同一用户连续短句，更像抽象接龙/歌词/排比，不应该继续把前面的候选当成强相关。
3. gate 里出现“SELF可主动破冰”这类理由时，主动性太强；没有明确指向机器人时不应该接。
4. 最后那句“像是把毛线团踢得到处都是……”就是旧候选没有被后续“接龙/歌词化”的消息降权导致的。

## 修复

- 候选半衰期默认从 22 秒调到 45 秒。
- 旧候选不会立刻消失，而是更慢地变成背景。
- 检测同一用户连续短句接龙/排比：
  - 如果没有 @ / 没有明确指向机器人
  - 自动降低这个用户之前候选的权重
  - 不继续主动接
- “破冰/无人接话/抽象问题”不再作为强主动回复理由。

## 使用

```powershell
cd E:\MiniClaw\miniclaw

python .\apply_memory_chain_fix.py

python -m py_compile .\src\clawmini\tools\qq_auto_reply.py

python app.py
```

## 可调参数

```powershell
$env:QQ_CANDIDATE_HALF_LIFE_SEC="45"
python app.py
```

建议范围：

```text
35~60 秒：更不容易忘
20~35 秒：更少接旧话
```

## 回滚

```powershell
copy .\src\clawmini\tools\qq_auto_reply.py.bak_memory_chain_fix .\src\clawmini\tools\qq_auto_reply.py
```
