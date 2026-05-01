#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DeepSeek 400 诊断脚本。

放在 E:\MiniClaw\miniclaw 下运行：
    python .\diagnose_deepseek_400.py

它会：
1. 自动寻找 qq_auto_reply_config.json，读取 reply_api_key/model/base_url。
2. 用最小 payload 请求 DeepSeek，打印 400 的真实响应 body。
3. 如果模型填成 deepseek-v4，会提示改成 deepseek-v4-pro 或 deepseek-v4-flash。
4. 不修改你的项目代码。
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path


def find_config(root: Path) -> Path | None:
    candidates = list(root.rglob("qq_auto_reply_config.json"))
    if not candidates:
        return None
    candidates.sort(key=lambda p: len(str(p)))
    return candidates[0]


def normalize_base_url(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return "https://api.deepseek.com"

    value = value.rstrip("/")

    # 用户如果填了完整接口，自动裁成 base_url
    for suffix in ("/chat/completions", "/v1/chat/completions"):
        if value.endswith(suffix):
            value = value[: -len(suffix)].rstrip("/")

    # DeepSeek 官方 OpenAI base_url 推荐不带 /v1；
    # 带 /v1 通常也兼容，但为了排除问题这里统一去掉。
    if value.endswith("/v1"):
        value = value[:-3].rstrip("/")

    return value or "https://api.deepseek.com"


def load_config() -> dict:
    root = Path.cwd()
    cfg_path = find_config(root)
    cfg = {}

    if cfg_path and cfg_path.exists():
        print(f"读取配置：{cfg_path}")
        try:
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"读取配置失败：{exc}")

    return cfg


def post_deepseek(api_key: str, model: str, base_url: str, with_thinking: bool = False) -> None:
    endpoint = normalize_base_url(base_url) + "/chat/completions"

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "你是一个简短回复的中文助手。"},
            {"role": "user", "content": "ping，回复两个字。"},
        ],
        "temperature": 0.3,
        "max_tokens": 60,
        "stream": False,
    }

    if with_thinking:
        payload["thinking"] = {"type": "disabled"}
        payload["reasoning_effort"] = "high"

    print("\n====== 请求信息 ======")
    print("endpoint:", endpoint)
    print("model:", model)
    print("with_thinking:", with_thinking)
    print("payload:", json.dumps({k: v for k, v in payload.items() if k != "messages"}, ensure_ascii=False))

    req = urllib.request.Request(
        endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            print("\n✅ 请求成功：")
            print(body[:2000])
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print("\n❌ HTTPError")
        print("code:", exc.code)
        print("reason:", exc.reason)
        print("body:")
        print(body[:4000])
    except Exception as exc:
        print("\n❌ 请求异常：", repr(exc))


def main() -> None:
    cfg = load_config()

    api_key = (
        str(cfg.get("reply_api_key", "") or "").strip()
        or os.getenv("DEEPSEEK_API_KEY", "").strip()
        or input("DeepSeek API Key: ").strip()
    )

    model = str(cfg.get("reply_api_model", "") or "").strip() or input("Model [deepseek-v4-pro]: ").strip() or "deepseek-v4-pro"
    base_url = str(cfg.get("reply_api_base_url", "") or "").strip() or input("Base URL [https://api.deepseek.com]: ").strip() or "https://api.deepseek.com"

    print("\n====== 配置检查 ======")
    print("base_url:", normalize_base_url(base_url))
    print("model:", model)
    print("api_key:", (api_key[:6] + "..." + api_key[-4:]) if len(api_key) > 12 else "未设置/过短")

    if not api_key:
        print("没有 API Key，无法测试。")
        sys.exit(1)

    if model in {"deepseek-v4", "deep seekv4", "deepseek v4", "deepseek-v4-pro "}:
        print("\n⚠️ 模型名疑似错误。DeepSeek V4 应填：deepseek-v4-pro 或 deepseek-v4-flash。")

    # 先测最小 payload，排除思考参数问题
    post_deepseek(api_key, model.strip(), base_url, with_thinking=False)

    # 再测带 thinking 的 payload
    post_deepseek(api_key, model.strip(), base_url, with_thinking=True)

    print("\n====== 判断方法 ======")
    print("1. 如果最小 payload 都 400：看上面的 body，通常是 model 名、base_url 或 key/账号权限问题。")
    print("2. 如果最小 payload 成功、with_thinking 失败：就是 thinking/reasoning_effort 参数问题。")
    print("3. 如果这两个都成功，但 app 里 400：就是 app 发给 DeepSeek 的 messages/payload 还有不兼容内容，需要把 app 的 HTTPError body 打出来。")


if __name__ == "__main__":
    main()
