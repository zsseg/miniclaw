# 视觉相关回复改成人类聊天口吻

## 目标

不要让 bot 在群里说这种系统味很重的话：

```text
这个表情包里的文字是……
根据图片识别结果……
可见文字……
低置信度……
图中文字……
```

要改成像真人接梗：

```text
喂，怎么还骂人呢！
你才猪头吧，哼。
这句我可看见了哦。
```

## 修复

1. 发送前清理视觉元话术：
   - 表情包
   - 图片识别
   - OCR
   - 可见文字
   - 采信度
   - 视觉线索
   - 图中文字

2. prompt 增加规则：
   - 最终发到群里的内容要像真人聊天；
   - 看到了图上的字，就直接像接梗一样回应；
   - 不要解释自己“识别到了什么”。

3. 不改主动开话题频率。
4. 不改图片采信度逻辑。

## 使用

```powershell
cd E:\MiniClaw\miniclaw

python .\fix_human_visual_reply.py

python -m py_compile .\src\clawmini\tools\qq_auto_reply.py

python app.py
```

## 回滚

```powershell
copy .\src\clawmini\tools\qq_auto_reply.py.bak_human_visual_reply .\src\clawmini\tools\qq_auto_reply.py
```
