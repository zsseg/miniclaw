# DeepSeek 400 诊断脚本

## 使用

把 `diagnose_deepseek_400.py` 放到项目根目录：

```text
E:\MiniClaw\miniclaw\
```

运行：

```powershell
cd E:\MiniClaw\miniclaw
python .\diagnose_deepseek_400.py
```

它不会修改项目，只会测试 DeepSeek API，并打印 400 的真实 body。

## 看结果

- 最小 payload 都 400：通常是 model、base_url、API Key、账号权限问题。
- 最小 payload 成功，with_thinking 失败：thinking/reasoning_effort 参数问题。
- 两个都成功，但 app 仍 400：app 里实际发出去的 payload 还有问题，需要继续打印 app 的请求 body。
