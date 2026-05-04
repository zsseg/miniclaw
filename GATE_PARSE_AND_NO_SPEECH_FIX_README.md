# 修复 gate 报错和不回复占位

## 对应日志问题

1. gate 解析失败：

```text
gate失败：Expecting value
gate失败：Unterminated string
```

2. 模型把“不回复”当成消息发出：

```text
（默默看着，不插话）
（不回复）
```

3. @ 自己却进了候选队列：

```text
[CQ:at,qq=391143621] 说话
wick 有点想法但先观察...
```

## 修复内容

- gate 不显式传 thinking
- gate max_tokens 提高
- gate JSON 宽松解析，半截 JSON 也能取 action
- gate 失败时从 custom_prompt 动态抽人设词兜底
- 补充识别 `[CQ:at,qq=机器人QQ]`
- 发送前拦截“（不回复）”“（默默看着，不插话）”这类占位
- prompt 里禁止输出不回复占位和内心戏旁白

## 使用

```powershell
cd E:\MiniClaw\miniclaw

python .\apply_gate_parse_and_no_speech_fix.py

python -m py_compile .\src\clawmini\tools\qq_auto_reply.py

python app.py
```

## 回滚

```powershell
copy .\src\clawmini\tools\qq_auto_reply.py.bak_gate_parse_and_no_speech .\src\clawmini\tools\qq_auto_reply.py
```
