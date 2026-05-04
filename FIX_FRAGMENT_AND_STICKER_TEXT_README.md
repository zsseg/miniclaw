# 修复主动开话题半截句 + 表情包清晰文字处理

## 重点

这版不改主动开话题频率，只解决“半截句子”。

例如会丢弃：

```text
唔…今天群里
唔…你们在打
```

原因一般是 DeepSeek thinking 消耗 reasoning tokens，原来 `max_tokens` 太小，content 被挤成半句话。

## 表情包清晰文字怎么处理

规则：

1. 识图时单独输出：
   - 可见文字
   - 文字清晰度
   - 可见内容
   - 可能情绪
   - 采信度

2. 可见文字是比较可靠的视觉事实。
   例如表情包里清楚写着：
   ```text
   你猪头吧
   ```
   这句话可以作为“图中文字”。

3. 但是表情包真正想表达的意思仍然低置信。
   不能直接断言“对方真的在骂我”，只能理解成：
   ```text
   可能是在拿表情包接梗/吐槽
   ```

4. 纯表情包通常仍不主动评论。
   只有当它像是在回应机器人刚才的话时，比如机器人刚说完，别人紧接着发一张带“你猪头吧”的表情包：
   - 会短暂等 OCR；
   - 如果文字清晰，进入候选；
   - 回复时用试探/接梗语气，而不是自信断言。

## 使用

```powershell
cd E:\MiniClaw\miniclaw

python .\fix_fragment_and_sticker_text.py

python -m py_compile .\src\clawmini\tools\qq_auto_reply.py

python app.py
```

## 回滚

```powershell
copy .\src\clawmini\tools\qq_auto_reply.py.bak_fragment_and_sticker_text .\src\clawmini\tools\qq_auto_reply.py
```
