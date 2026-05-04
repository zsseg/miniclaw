# 表情选择：不避开最近，只保证整体多样化

## 改动

上一版会避开最近发过的 N 个表情。你说不需要这个，所以这版去掉“recent avoid”。

现在逻辑是：

```text
不管最近发没发过
只看整个表情池的 use_count
优先从使用次数最低的一批里随机挑
```

这样效果是：

- 不会因为“刚发过”而硬排除；
- 但长期不会总发同一个；
- 新收集到的表情因为 use_count=0，会更容易被用到；
- 表情池越大，候选池会稍微放宽，避免太机械。

## 使用

```powershell
cd E:\MiniClaw\miniclaw

python .\fix_emote_diversity_no_recent_avoid.py

python -m py_compile .\src\clawmini\tools\qq_auto_reply.py

python app.py
```

## 不再使用

```powershell
$env:QQ_EMOTE_AVOID_RECENT_N="8"
```

这个参数可以不用管了。

## 回滚

```powershell
copy .\src\clawmini\tools\qq_auto_reply.py.bak_emote_diversity_no_recent_avoid .\src\clawmini\tools\qq_auto_reply.py
```
