# 纯图不主动评论 + 戳一戳 @ 戳的人

## 修复 1：纯图/表情包不主动评论

日志里这种情况不应该回复：

```text
[CQ:image,summary=[动画表情],...]
bot: 哼，豆豆你这是在笑我吗？那张图一看就不怀好意喵。
```

修复后：

- 纯图片 / 纯动画表情：
  - 只记录上下文
  - 如果已有识图预热逻辑，就后台预热识图
  - 不进入社交 gate
  - 不进入候选队列
  - 不主动回复

- 只有这些情况才会回复图片：
  - 用户明确问“这图什么意思 / 这图啥意思 / 什么梗”
  - 用户 @ bot
  - 图片消息本身带真实文本配文

## 修复 2：戳一戳 @ 戳的人

群聊戳一戳回复会改成：

```text
[CQ:at,qq=戳的人] 喵？！谁戳我尾巴！
```

私聊不加 @。

## 使用

```powershell
cd E:\MiniClaw\miniclaw

python .\apply_image_guard_and_poke_at.py

python -m py_compile .\src\clawmini\tools\qq_auto_reply.py

python app.py
```

## 回滚

```powershell
copy .\src\clawmini\tools\qq_auto_reply.py.bak_image_guard_poke_at .\src\clawmini\tools\qq_auto_reply.py
```
