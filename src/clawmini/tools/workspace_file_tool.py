"""工作区通用文件操作工具。"""

from __future__ import annotations

import base64
import ctypes
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from clawmini.core.security import ensure_path_in_workspace
from clawmini.tools.base import BaseTool
from clawmini.tools.registry import tool_plugin
from clawmini.types import ToolResult
from typing import Callable


@tool_plugin("workspace_files")
class WorkspaceFileTool(BaseTool):
    """在工作区内创建、修改、删除、重命名和查看任意文件。"""

    name = "workspace_files"
    description = "在工作区内创建、修改、删除、重命名、读取和列出任意文件或目录；删除会送入回收站。也支持 list_recycle（查看回收站内容）、empty_recycle（清空回收站）、restore_recycle（还原单个文件到原始路径，参数 recycle_name）和 delete_recycle_item（彻底删除单个文件，参数 recycle_name）命令。用户说「清空回收站」时请调用 empty_recycle 命令。"
    parameters_schema = {
        "type": "object",
        "properties": {
            "command": {"type": "string"},
            "path": {"type": "string"},
            "source_path": {"type": "string"},
            "target_path": {"type": "string"},
            "content": {"type": "string"},
            "content_base64": {"type": "string"},
            "encoding": {"type": "string"},
            "recursive": {"type": "boolean"},
            "include_hidden": {"type": "boolean"},
            "limit": {"type": "integer"},
            "overwrite": {"type": "boolean"},
            "max_chars": {"type": "integer"},
        },
        "required": ["command"],
    }

    def run(self, arguments: dict[str, Any], progress_callback: Callable[[str], None] | None = None) -> ToolResult:
        try:
            return self._run_impl(arguments)
        except ValueError as ve:
            return ToolResult(False, f"参数错误：{ve}")
        except FileNotFoundError as fnf:
            return ToolResult(False, f"文件未找到：{fnf}")
        except PermissionError as pe:
            return ToolResult(False, f"权限错误：{pe}")
        except OSError as oe:
            return ToolResult(False, f"文件系统错误：{oe}")
        except Exception as exc:
            return ToolResult(False, f"操作失败：{exc}")

    def _run_impl(self, arguments: dict[str, Any]) -> ToolResult:
        command = str(arguments.get("command", "")).strip().lower()
        # 兼容模型可能输出的 command 别名
        command_aliases = {
            "read_file": "read",
            "create_file": "create",
            "write_file": "write",
            "delete_file": "delete",
            "rename_file": "rename",
            "list_dir": "list",
            "list_directory": "list",
        }
        command = command_aliases.get(command, command)
        if command == "list":
            return self._list(arguments)
        if command == "read":
            return self._read(arguments)
        if command == "create":
            return self._create(arguments)
        if command == "write":
            return self._write(arguments)
        if command == "append":
            return self._append(arguments)
        if command == "rename":
            return self._rename(arguments)
        if command == "delete":
            return self._delete(arguments)
        if command == "info":
            return self._info(arguments)
        if command in ("list_recycle", "list_recycle_bin", "recycle_list"):
            return self._list_recycle(arguments)
        if command in ("empty_recycle", "empty_recycle_bin", "clear_recycle"):
            return self._empty_recycle(arguments)
        if command in ("restore_recycle", "restore_recycle_item", "recycle_restore"):
            return self._restore_recycle_item(arguments)
        if command in ("delete_recycle_item", "permanent_delete_recycle", "recycle_delete"):
            return self._permanent_delete_recycle_item(arguments)
        return ToolResult(False, f"不支持的 command: {command}")

    def _resolve_path(self, raw_path: str) -> Path:
        wd = self._abs_workspace()
        candidate = Path(str(raw_path).strip() or ".")
        if not candidate.is_absolute():
            candidate = wd / candidate
        return ensure_path_in_workspace(candidate, wd)

    def _abs_workspace(self) -> Path:
        """返回绝对路径的 workspace 目录，供 relative_to 等方法使用。"""
        return self.workspace_dir.resolve()

    def _decode_content(self, arguments: dict[str, Any]) -> bytes:
        encoding = str(arguments.get("encoding", "utf-8")).strip().lower()
        if encoding == "base64":
            raw = str(arguments.get("content_base64", arguments.get("content", ""))).strip()
            return base64.b64decode(raw.encode("utf-8")) if raw else b""
        content = str(arguments.get("content", ""))
        return content.encode("utf-8")

    def _read_text_preview(self, path: Path, max_chars: int) -> str:
        try:
            return path.read_text(encoding="utf-8", errors="replace")[:max_chars]
        except Exception:
            data = path.read_bytes()[: max_chars // 2]
            preview = base64.b64encode(data).decode("ascii")
            return f"[二进制预览 base64] {preview}"

    def _list(self, arguments: dict[str, Any]) -> ToolResult:
        raw_path = str(arguments.get("path", "")).strip() or "."
        recursive = bool(arguments.get("recursive", False))
        include_hidden = bool(arguments.get("include_hidden", False))
        limit = int(arguments.get("limit", 200))
        limit = max(1, min(limit, 1000))

        path = self._resolve_path(raw_path)
        if not path.exists():
            return ToolResult(False, f"路径不存在：{path}")

        if path.is_file():
            lines = [f"FILE {path.relative_to(self._abs_workspace())}"]
        else:
            items: list[str] = []
            iterator = path.rglob("*") if recursive else path.iterdir()
            for item in iterator:
                if not include_hidden and any(part.startswith(".") for part in item.relative_to(path).parts):
                    continue
                rel = item.relative_to(self._abs_workspace())
                prefix = "[D]" if item.is_dir() else "[F]"
                items.append(f"{prefix} {rel}")
                if len(items) >= limit:
                    break
            items.sort()
            lines = [f"目录：{path.relative_to(self._abs_workspace())}", *items]
        return ToolResult(True, "\n".join(lines), {"path": str(path), "count": max(len(lines) - 1, 0)})

    def _read(self, arguments: dict[str, Any]) -> ToolResult:
        path = self._resolve_path(str(arguments.get("path", "")))
        max_chars = int(arguments.get("max_chars", 12000))
        max_chars = max(1, min(max_chars, 50000))
        if not path.exists() or not path.is_file():
            return ToolResult(False, f"文件不存在：{path}")
        content = self._read_text_preview(path, max_chars)
        return ToolResult(True, content, {"path": str(path), "size": path.stat().st_size})

    def _create(self, arguments: dict[str, Any]) -> ToolResult:
        path = self._resolve_path(str(arguments.get("path", "")))
        overwrite = bool(arguments.get("overwrite", False))
        if path.exists() and not overwrite:
            return ToolResult(False, f"文件已存在：{path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        data = self._decode_content(arguments)
        if data:
            path.write_bytes(data)
        else:
            path.touch(exist_ok=True)
        return ToolResult(True, f"已创建文件：{path}", {"path": str(path), "bytes": path.stat().st_size})

    def _write(self, arguments: dict[str, Any]) -> ToolResult:
        path = self._resolve_path(str(arguments.get("path", "")))
        path.parent.mkdir(parents=True, exist_ok=True)
        data = self._decode_content(arguments)
        path.write_bytes(data)
        return ToolResult(True, f"已写入文件：{path}", {"path": str(path), "bytes": path.stat().st_size})

    def _append(self, arguments: dict[str, Any]) -> ToolResult:
        path = self._resolve_path(str(arguments.get("path", "")))
        path.parent.mkdir(parents=True, exist_ok=True)
        data = self._decode_content(arguments)
        mode = "ab" if data else "ab"
        with path.open(mode) as f:
            if data:
                f.write(data)
        return ToolResult(True, f"已追加写入文件：{path}", {"path": str(path), "bytes": path.stat().st_size})

    def _rename(self, arguments: dict[str, Any]) -> ToolResult:
        source_raw = str(arguments.get("source_path", arguments.get("path", ""))).strip()
        target_raw = str(arguments.get("target_path", "")).strip()
        if not source_raw or not target_raw:
            return ToolResult(False, "rename 需要 source_path 和 target_path。")
        source = self._resolve_path(source_raw)
        target = self._resolve_path(target_raw)
        if not source.exists():
            return ToolResult(False, f"源文件不存在：{source}")
        if target.exists():
            return ToolResult(False, f"目标已存在：{target}")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(target))
        return ToolResult(True, f"已重命名/移动：{source} -> {target}", {"source": str(source), "target": str(target)})

    def _delete(self, arguments: dict[str, Any]) -> ToolResult:
        path = self._resolve_path(str(arguments.get("path", "")))
        if not path.exists():
            return ToolResult(False, f"文件或目录不存在：{path}")
        error = self._send_to_recycle_bin(path)
        if error:
            return ToolResult(False, error)
        return ToolResult(True, f"已送入回收站：{path}", {"path": str(path), "recycled": True})

    def _info(self, arguments: dict[str, Any]) -> ToolResult:
        path = self._resolve_path(str(arguments.get("path", "")))
        if not path.exists():
            return ToolResult(False, f"路径不存在：{path}")
        stat = path.stat()
        kind = "目录" if path.is_dir() else "文件"
        return ToolResult(
            True,
            f"{kind}：{path}\n大小：{stat.st_size} 字节\n修改时间：{stat.st_mtime}",
            {"path": str(path), "is_dir": path.is_dir(), "size": stat.st_size},
        )

    def _send_to_recycle_bin(self, path: Path) -> str | None:
        if os.name != "nt":
            trash_dir = self.workspace_dir / ".recycle_bin"
            trash_dir.mkdir(parents=True, exist_ok=True)
            target = trash_dir / path.name
            if target.exists():
                suffix = 1
                while (trash_dir / f"{path.stem}_{suffix}{path.suffix}").exists():
                    suffix += 1
                target = trash_dir / f"{path.stem}_{suffix}{path.suffix}"
            shutil.move(str(path), str(target))
            # 保存元数据：原始路径
            self._save_recycle_meta(target.name, str(path.resolve()))
            return None

        from ctypes import wintypes

        class SHFILEOPSTRUCTW(ctypes.Structure):
            _fields_ = [
                ("hwnd", wintypes.HWND),
                ("wFunc", wintypes.UINT),
                ("pFrom", wintypes.LPCWSTR),
                ("pTo", wintypes.LPCWSTR),
                ("fFlags", wintypes.WORD),
                ("fAnyOperationsAborted", wintypes.BOOL),
                ("hNameMappings", wintypes.LPVOID),
                ("lpszProgressTitle", wintypes.LPCWSTR),
            ]

        FO_DELETE = 3
        FOF_ALLOWUNDO = 0x0040
        FOF_NOCONFIRMATION = 0x0010
        FOF_SILENT = 0x0004
        FOF_NOERRORUI = 0x0400

        op = SHFILEOPSTRUCTW()
        op.hwnd = None
        op.wFunc = FO_DELETE
        op.pFrom = str(path) + "\0"
        op.pTo = None
        op.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT | FOF_NOERRORUI
        op.fAnyOperationsAborted = False
        op.hNameMappings = None
        op.lpszProgressTitle = None
        result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
        if result != 0:
            return f"回收站删除失败，错误码={result}"
        if op.fAnyOperationsAborted:
            return "回收站删除已中止"
        return None

    def _list_recycle(self, arguments: dict[str, Any]) -> ToolResult:
        """列出回收站内容。"""
        lines = []
        count = 0

        # 本地 .recycle_bin 目录
        recycle_dir = self.workspace_dir / ".recycle_bin"
        if recycle_dir.exists():
            for f in sorted(recycle_dir.iterdir()):
                if f.is_file():
                    size = f.stat().st_size
                    size_str = f"{size} B" if size < 1024 else f"{size / 1024:.1f} KB"
                    mtime = datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                    lines.append(f"[本地回收站] {f.name} ({size_str}, {mtime})")
                    count += 1

        # Windows 系统回收站
        if os.name == "nt":
            win_count = self._query_recycle_bin_count()
            if win_count > 0:
                lines.append(f"[系统回收站] 约 {win_count} 个文件")
                count += win_count

        if count == 0:
            return ToolResult(True, "回收站是空的。", {"count": 0})
        return ToolResult(True, "\n".join(lines), {"count": count})

    def _empty_recycle(self, arguments: dict[str, Any]) -> ToolResult:
        """清空回收站。"""
        messages = []

        # 清空本地 .recycle_bin
        recycle_dir = self.workspace_dir / ".recycle_bin"
        if recycle_dir.exists():
            try:
                for f in recycle_dir.iterdir():
                    try:
                        if f.is_file():
                            f.unlink()
                        elif f.is_dir():
                            shutil.rmtree(str(f))
                    except Exception as exc:
                        messages.append(f"删除 {f.name} 失败：{exc}")
                try:
                    if recycle_dir.exists() and not any(recycle_dir.iterdir()):
                        recycle_dir.rmdir()
                except Exception:
                    pass
                messages.append("本地回收站已清空。")
            except Exception as exc:
                messages.append(f"清空本地回收站失败：{exc}")

        # Windows 系统回收站
        if os.name == "nt":
            try:
                from ctypes import wintypes as _wintypes
                SHEmptyRecycleBinW = ctypes.windll.shell32.SHEmptyRecycleBinW
                SHEmptyRecycleBinW.restype = ctypes.c_long
                SHEmptyRecycleBinW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint]
                SHERB_NOCONFIRMATION = 0x00000001
                SHERB_NOPROGRESSUI = 0x00000002
                SHERB_NOSOUND = 0x00000004
                result = SHEmptyRecycleBinW(None, None, SHERB_NOCONFIRMATION | SHERB_NOPROGRESSUI | SHERB_NOSOUND)
                if result == 0:
                    messages.append("系统回收站已清空。")
                else:
                    messages.append(f"清空系统回收站失败，错误码={result}")
            except Exception as exc:
                messages.append(f"清空系统回收站异常：{exc}")

        output = "；".join(messages) or "回收站已是空的。"
        return ToolResult(True, output, {"cleared": True})

    def _restore_recycle_item(self, arguments: dict[str, Any]) -> ToolResult:
        """还原单个回收站文件到原始路径。"""
        recycle_name = str(arguments.get("recycle_name", "")).strip()
        if not recycle_name:
            return ToolResult(False, "缺少 recycle_name 参数。")

        recycle_dir = self.workspace_dir / ".recycle_bin"
        recycle_file = recycle_dir / recycle_name
        if not recycle_file.exists():
            return ToolResult(False, f"回收站中找不到文件：{recycle_name}")

        # 读取元数据获取原始路径
        source_path = self._get_recycle_meta(recycle_name)
        if source_path and Path(source_path).exists():
            target = Path(source_path)
        elif source_path:
            target = Path(source_path)
            target.parent.mkdir(parents=True, exist_ok=True)
        else:
            target = self.workspace_dir / recycle_name

        try:
            shutil.move(str(recycle_file), str(target))
            self._remove_recycle_meta(recycle_name)
            return ToolResult(True, f"已还原到：{target}", {"restored_to": str(target)})
        except Exception as exc:
            return ToolResult(False, f"还原失败：{exc}")

    def _permanent_delete_recycle_item(self, arguments: dict[str, Any]) -> ToolResult:
        """彻底删除单个回收站文件。"""
        recycle_name = str(arguments.get("recycle_name", "")).strip()
        if not recycle_name:
            return ToolResult(False, "缺少 recycle_name 参数。")

        recycle_dir = self.workspace_dir / ".recycle_bin"
        recycle_file = recycle_dir / recycle_name
        if not recycle_file.exists():
            return ToolResult(False, f"回收站中找不到文件：{recycle_name}")

        try:
            recycle_file.unlink()
            self._remove_recycle_meta(recycle_name)
            return ToolResult(True, f"已永久删除：{recycle_name}")
        except Exception as exc:
            return ToolResult(False, f"删除失败：{exc}")

    @staticmethod
    def _save_recycle_meta(recycle_name: str, source_path: str) -> None:
        """保存回收站元数据（原始路径），供 UI 还原使用。"""
        meta_path = Path(__file__).resolve().parent.parent.parent.parent / "workspace" / ".recycle_bin" / ".recycle_meta.json"
        # fallback: 从 workspace_dir 推断
        try:
            import json
            # 尝试从 worksapce 目录定位
            from pathlib import Path as _P
            candidate = _P.cwd() / "workspace" / ".recycle_bin" / ".recycle_meta.json"
            if candidate.parent.exists() or candidate.parent.parent.exists():
                meta_path = candidate
        except Exception:
            pass
        try:
            meta_path.parent.mkdir(parents=True, exist_ok=True)
            data = {}
            if meta_path.exists():
                raw = meta_path.read_text(encoding="utf-8")
                if raw.strip():
                    data = json.loads(raw)
            if not isinstance(data, dict):
                data = {}
            data[recycle_name] = source_path
            meta_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    @staticmethod
    def _get_recycle_meta(recycle_name: str) -> str | None:
        """获取回收站文件的原始路径。"""
        meta_path = Path(__file__).resolve().parent.parent.parent.parent / "workspace" / ".recycle_bin" / ".recycle_meta.json"
        try:
            import json
            if meta_path.exists():
                raw = meta_path.read_text(encoding="utf-8")
                if raw.strip():
                    data = json.loads(raw)
                    if isinstance(data, dict):
                        return data.get(recycle_name)
        except Exception:
            pass
        return None

    @staticmethod
    def _remove_recycle_meta(recycle_name: str) -> None:
        """删除回收站文件的元数据记录。"""
        meta_path = Path(__file__).resolve().parent.parent.parent.parent / "workspace" / ".recycle_bin" / ".recycle_meta.json"
        try:
            import json
            if meta_path.exists():
                raw = meta_path.read_text(encoding="utf-8")
                if raw.strip():
                    data = json.loads(raw)
                    if isinstance(data, dict):
                        data.pop(recycle_name, None)
                        meta_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    @staticmethod
    def _query_recycle_bin_count() -> int:
        """查询 Windows 回收站中的文件数量。"""
        try:
            from ctypes import wintypes as _wintypes

            class SHQUERYRBINFO(ctypes.Structure):
                _fields_ = [
                    ("cbSize", _wintypes.DWORD),
                    ("i64Size", ctypes.c_int64),
                    ("i64NumItems", ctypes.c_int64),
                ]

            info = SHQUERYRBINFO()
            info.cbSize = ctypes.sizeof(SHQUERYRBINFO)
            result = ctypes.windll.shell32.SHQueryRecycleBinW(None, ctypes.byref(info))
            if result == 0:
                return int(info.i64NumItems)
        except Exception:
            pass
        return 0