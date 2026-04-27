"""历史存储模块：将对话持久化到 JSON。"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from clawmini.types import Message


class HistoryStore:
    """会话持久化存储。"""

    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> list[Message]:
        """加载历史消息。"""
        if not self.path.exists():
            return []
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        return [Message(**item) for item in raw]

    def save(self, messages: list[Message]) -> None:
        """保存历史消息。"""
        payload = [asdict(m) for m in messages]
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
