# 动态人设 + 候选权值衰减

## 这版解决什么

不把人设、兴趣点、名字写死在代码里；这些都来自当前配置里的 `custom_prompt`，以及最近聊天自然推断。

候选回复也不再简单压缩成最近 N 条，而是改成权值衰减：

```text
候选最终权重 = 基础权重 × 时间衰减
```

基础权重来自：

- gate confidence
- reply_relevance
- 是否明确 @ 自己
- 是否是显式图片问题
- 是否只是纯图/纯表情背景

时间衰减默认半衰期 22 秒。旧候选不会立刻删除，但会慢慢变成低权重背景，不再污染新回复。

## 使用

```powershell
cd E:\MiniClaw\miniclaw

python .\apply_dynamic_speaker_weight_decay.py

python -m py_compile .\src\clawmini\tools\qq_auto_reply.py

python app.py
```

## 可调参数

```powershell
$env:QQ_CANDIDATE_HALF_LIFE_SEC="22"
python app.py
```

建议范围：

```text
15~25 秒：更像群聊即时反应
25~45 秒：更愿意记住上下文
```

## 回滚

```powershell
copy .\src\clawmini\tools\qq_auto_reply.py.bak_dynamic_speaker_weight .\src\clawmini\tools\qq_auto_reply.py
```
