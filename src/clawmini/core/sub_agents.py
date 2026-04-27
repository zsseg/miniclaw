"""子 Agent 模块：提供主 Agent 可委托的专长能力。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from clawmini.core.security import ensure_path_in_workspace


@dataclass(slots=True)
class FileAnalysisAgent:
    """文件分析子 Agent。"""

    workspace_dir: Path

    def analyze_file(self, raw_path: str) -> str:
        """分析目标文本文件，返回简要摘要。"""
        target = Path(raw_path)
        if not target.is_absolute():
            target = self.workspace_dir / target
        path = ensure_path_in_workspace(target, self.workspace_dir)
        if not path.exists() or not path.is_file():
            return f"文件不存在：{path}"

        content = path.read_text(encoding="utf-8", errors="ignore")
        lines = content.splitlines()
        headings = [line.strip() for line in lines if line.strip().startswith("#")][:5]
        return (
            f"文件分析结果：{path.name}\n"
            f"- 字符数：{len(content)}\n"
            f"- 行数：{len(lines)}\n"
            f"- 头部标题：{headings if headings else '无'}"
        )
