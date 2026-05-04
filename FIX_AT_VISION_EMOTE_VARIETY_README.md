# 只 @ 也真正 @ 上 + 识图日志 + 表情包多样化

## 1. 只 @ 也真正 @

模型如果输出：

```text
@2650636447
```

会转换成 OneBot 消息段：

```json
[
  {"type": "at", "data": {"qq": 2650636447}}
]
```

如果输出：

```text
@2650636447 你怎么回事
```

会转换成：

```json
[
  {"type": "at", "data": {"qq": 2650636447}},
  {"type": "text", "data": {"text": " 你怎么回事"}}
]
```

不会再把 `@数字` 当普通文本发出去，也不会拦截“只有 @”。

## 2. 怎么知道图片有没有提取文字

图片后台识图完成后，会输出日志：

```text
[QQVision] group/597912657 user/2114683026 image#1: 文字=你猪头吧 | 清晰度=高 | 内容=...
```

如果没提取到：

```text
[QQVision] group/597912657 user/2114683026 image#1: 文字=无/不清楚 | 清晰度=无 | 内容=...
```

如果没有任何识图结果：

```text
[QQVision] group/... image#1: 无识别结果；可能未配置 DASHSCOPE_API_KEY、图片下载失败，或识图返回为空。
```

## 3. 表情包发送太单一

`_pick_collected_emote_for_reply` 改成：

- 避开最近发过的 N 个表情；
- 按 `use_count` 降权；
- 给图片表情一点点加权，普通 face 稍降权；
- 加随机扰动；
- 池子太小时仍可回退，不会发不出来。

可调：

```powershell
$env:QQ_EMOTE_AVOID_RECENT_N="8"
$env:QQ_EMOTE_POOL_TTL_HOURS="24"
```

## 使用

```powershell
cd E:\MiniClaw\miniclaw

python .\fix_at_vision_emote_variety.py

python -m py_compile .\src\clawmini\tools\qq_auto_reply.py

python app.py
```

## 回滚

```powershell
copy .\src\clawmini\tools\qq_auto_reply.py.bak_at_vision_emote_variety .\src\clawmini\tools\qq_auto_reply.py
```
