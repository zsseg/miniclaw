# 普通图片可以复读，但不当表情包

## 目标

你说得对：普通图片不是表情包，但它可以参与复读。

所以要拆成两层：

```text
表情池 / 随机发表情：
只收 QQ face、动画表情、明确表情包图片

视觉复读流：
可以包含 QQ face、动画表情、普通图片
```

## 效果

普通图片：

```text
[CQ:image,file=xxx.jpg,sub_type=0,...]
```

可以在同款复读时被跟发，但不会进 `qq_emote_pool.json`，也不会以后被当作随机表情发出来。

动画表情：

```text
[CQ:image,summary=[动画表情],sub_type=1,...]
```

仍然按表情处理。

## 日志区别

普通图片会看到：

```text
[QQEmote] group/...: pure=True visual=1 emotes=0 plain_images=1 exact=...
```

动画表情会看到：

```text
[QQEmote] group/...: pure=True visual=1 emotes=1 plain_images=0 exact=...
```

## 使用

```powershell
cd E:\MiniClaw\miniclaw

python .\fix_plain_image_repeat_not_emote.py

python -m py_compile .\src\clawmini\tools\qq_auto_reply.py

python app.py
```

## 回滚

```powershell
copy .\src\clawmini\tools\qq_auto_reply.py.bak_plain_image_repeat_not_emote .\src\clawmini\tools\qq_auto_reply.py
```
