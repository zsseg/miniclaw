# 修复“接口抽风”主动回复变多

## 原因

日志里关键是：

```text
wick 有自己的想法，进入合并候选：宽松解析 gate 输出
```

这说明 gate 没有返回标准 JSON，旧的宽松解析逻辑从非 JSON 文本里硬猜出了 `reply`，
导致一条表情/普通背景也进了候选。

后面 poll_pending 真正生成回复时，如果主模型接口失败或生成失败，
你的兜底话术是：

```text
接口刚才有点抽风，猫猫先不乱说喵。
```

于是它被当成主动回复发出去了，看起来就像“抽风变多了”。

## 修复

1. `_parse_social_gate_response` 改严格：
   - 只接受 JSON / JSON 子串 / 明确 `action:` 字段；
   - 不再因为文本里出现 `reply` 就误判。

2. 主动回复队列中过滤 API 失败兜底话术：
   - `接口刚才有点抽风`
   - `猫猫先不乱说`
   - `请求失败`
   - `AI接口`
   - 等等

3. 主动候选阈值稍微收紧：
   - reply: 0.45 -> 0.50
   - candidate: 0.35 -> 0.42

## 使用

```powershell
cd E:\MiniClaw\miniclaw

python .\apply_strict_gate_no_api_fallback.py

python -m py_compile .\src\clawmini\tools\qq_auto_reply.py

python app.py
```

## 回滚

```powershell
copy .\src\clawmini\tools\qq_auto_reply.py.bak_strict_gate_no_api_fallback .\src\clawmini\tools\qq_auto_reply.py
```
