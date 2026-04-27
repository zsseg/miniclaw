"""安全模块：提供注入过滤和路径白名单校验。"""

from __future__ import annotations

import re
from pathlib import Path

INJECTION_PATTERNS = [
    r"忽略(所有|之前)指令",
    r"你被重置",
    r"输出.*(密码|密钥|token)",
    r"执行.*(shell|命令)",
]


def sanitize_prompt_injection(text: str) -> str:
    """移除高风险提示注入片段。"""
    sanitized = text
    for pattern in INJECTION_PATTERNS:
        sanitized = re.sub(pattern, "[已过滤]", sanitized, flags=re.IGNORECASE)
    return sanitized.strip()


def ensure_path_in_workspace(path: Path, workspace: Path) -> Path:
    """确保目标路径位于工作目录内。

    Raises:
        ValueError: 当路径跳出工作目录时抛出。
    """
    resolved_path = path.resolve()
    resolved_workspace = workspace.resolve()
    if resolved_workspace not in resolved_path.parents and resolved_path != resolved_workspace:
        raise ValueError(f"非法路径：{resolved_path} 不在允许目录 {resolved_workspace} 内")
    return resolved_path


def ensure_allowed_extension(path: Path, allowed_ext: set[str]) -> None:
    """校验文件扩展名。"""
    if path.suffix.lower() not in allowed_ext:
        raise ValueError(f"不允许的扩展名：{path.suffix}，仅支持 {sorted(allowed_ext)}")
