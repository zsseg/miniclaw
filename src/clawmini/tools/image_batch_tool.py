"""批量图片处理工具。"""

from __future__ import annotations

import shutil
import re
import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from pathlib import Path
from typing import Any, Callable

from PIL import Image  # type: ignore[import-not-found]

from clawmini.core.security import ensure_path_in_workspace
from clawmini.tools.base import BaseTool
from clawmini.types import ToolResult


class ImageBatchTool(BaseTool):
    """批量处理图片：调整尺寸、转换格式、重命名。"""

    name = "image_batch_tool"
    description = "批量调整图片尺寸、格式转换与序号重命名，生成处理报告"
    parameters_schema = {
        "type": "object",
        "properties": {
            "input_dir": {"type": "string"},
            "output_dir": {"type": "string"},
            "request": {"type": "string"},
            "target_format": {"type": "string"},
            "width": {"type": "integer"},
            "height": {"type": "integer"},
            "overwrite": {"type": "boolean"},
            "keep_ratio": {"type": "boolean"},
            "confirm_lossy": {"type": "boolean"},
            "per_image_timeout_sec": {"type": "number"},
            "start_index": {"type": "integer"},
            "pad_width": {"type": "integer"},
            "pattern": {"type": "string"},
            "task_id": {"type": "string"},
        },
        "required": ["input_dir", "output_dir"],
    }

    def __init__(self, workspace_dir: Path) -> None:
        super().__init__(workspace_dir)
        self.canceled_tasks: set[str] = set()
        self.task_state: dict[str, dict[str, Any]] = {}

    def run(self, arguments: dict[str, Any], progress_callback: Callable[[str], None] | None = None) -> ToolResult:
        command = str(arguments.get("command", "process"))
        if command == "cancel_task":
            task_id = str(arguments.get("task_id", ""))
            if not task_id:
                return ToolResult(False, "cancel_task 需要 task_id")
            self.canceled_tasks.add(task_id)
            return ToolResult(True, f"任务已标记取消：{task_id}")
        if command == "task_status":
            task_id = str(arguments.get("task_id", ""))
            if not task_id:
                return ToolResult(False, "task_status 需要 task_id")
            state = self.task_state.get(task_id)
            if not state:
                return ToolResult(False, f"任务不存在：{task_id}")
            return ToolResult(
                True,
                f"task_id={task_id}; status={state['status']}; progress={state['processed']}/{state['total']}",
                state,
            )
        return self._process(arguments)

    def _process(self, arguments: dict[str, Any]) -> ToolResult:
        task_id = str(arguments.get("task_id", uuid.uuid4().hex[:8]))

        parsed = self._parse_natural_language_request(str(arguments.get("request", "")))
        merged = {**arguments, **parsed}

        input_dir = ensure_path_in_workspace(self.workspace_dir / str(merged.get("input_dir", "images")), self.workspace_dir)
        output_dir = ensure_path_in_workspace(self.workspace_dir / str(merged.get("output_dir", "output")), self.workspace_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        target_format = str(merged.get("target_format", "png")).lower()
        width = int(merged.get("width", 1024))
        height = int(merged.get("height", 768))
        keep_ratio = bool(merged.get("keep_ratio", False))
        overwrite = bool(merged.get("overwrite", False))
        confirm_lossy = bool(merged.get("confirm_lossy", False))
        per_image_timeout_sec = float(merged.get("per_image_timeout_sec", 30.0))
        start_index = int(merged.get("start_index", 1))
        pad_width = int(merged.get("pad_width", 3))
        pattern = str(merged.get("pattern", "img_{index}"))

        files = [
            p
            for p in sorted(input_dir.iterdir())
            if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp"}
        ]

        if not files:
            return ToolResult(False, f"输入目录中没有可处理图片：{input_dir}")

        if any(p.suffix.lower() == ".gif" for p in files) and target_format == "png":
            warning = "检测到 GIF 转 PNG 可能丢失动画，已按静态图处理。"
            if not confirm_lossy:
                return ToolResult(False, "检测到 GIF→PNG 可能丢失动画，请显式传入 confirm_lossy=true 后重试。")
        else:
            warning = ""

        self._ensure_disk_space(files)

        self.task_state[task_id] = {
            "task_id": task_id,
            "status": "running",
            "processed": 0,
            "total": len(files),
            "success": 0,
            "failed_count": 0,
            "failed": [],
            "batch_mode": len(files) > 100,
        }

        success = 0
        failed: list[str] = []
        for idx, src in enumerate(files, start=start_index):
            if task_id in self.canceled_tasks:
                self.task_state[task_id]["status"] = "canceled"
                break

            name = pattern.format(index=str(idx).zfill(pad_width)) + f".{target_format}"
            dst = output_dir / name
            if dst.exists() and not overwrite:
                failed.append(f"{src.name}: 目标已存在")
                self.task_state[task_id]["failed_count"] = len(failed)
                self.task_state[task_id]["failed"] = failed
                self.task_state[task_id]["processed"] += 1
                continue

            try:
                self._process_single_image(
                    src=src,
                    dst=dst,
                    width=width,
                    height=height,
                    keep_ratio=keep_ratio,
                    target_format=target_format,
                    timeout_sec=per_image_timeout_sec,
                )
                success += 1
                self.task_state[task_id]["success"] = success
            except TimeoutError:
                failed.append(f"{src.name}: 单图处理超时（>{per_image_timeout_sec:.1f}s）")
                self.task_state[task_id]["failed_count"] = len(failed)
                self.task_state[task_id]["failed"] = failed
            except Exception as exc:  # noqa: BLE001
                failed.append(f"{src.name}: {exc}")
                self.task_state[task_id]["failed_count"] = len(failed)
                self.task_state[task_id]["failed"] = failed
            finally:
                self.task_state[task_id]["processed"] += 1

        if self.task_state[task_id]["status"] != "canceled":
            self.task_state[task_id]["status"] = "completed"

        report = (
            f"task_id={task_id}; 成功={success}; 失败={len(failed)}"
            + (f"; 警告={warning}" if warning else "")
        )
        if failed:
            report += "\n失败详情:\n" + "\n".join(failed[:20])
        meta = {
            "task_id": task_id,
            "success": success,
            "failed": failed,
            "progress": {
                "processed": self.task_state[task_id]["processed"],
                "total": self.task_state[task_id]["total"],
                "status": self.task_state[task_id]["status"],
            },
        }
        return ToolResult(True, report, meta)

    def _parse_natural_language_request(self, request: str) -> dict[str, Any]:
        """把中文图片处理需求解析成结构化参数。"""
        text = request.strip()
        if not text:
            return {}

        parsed: dict[str, Any] = {}

        def _clean_path_token(token: str) -> str:
            token = token.strip().strip("。！？!?,，；;：:\"'“”")
            token = token.rstrip("/\\")
            return token or "."

        dir_match = re.search(r"(?:从\s*)?([A-Za-z0-9_.\\/-]+)\s*(?:文件夹|目录)(?:中|里|内)?", text)
        if dir_match:
            parsed["input_dir"] = _clean_path_token(dir_match.group(1))
        dir_match = re.search(r"(?:输出|保存到|导出到|放到)\s*([A-Za-z0-9_.\\/-]+)", text)
        if dir_match:
            parsed["output_dir"] = _clean_path_token(dir_match.group(1))

        explicit_format = re.search(r"(?:转换为|转成|输出为|保存为|保存成|导出为)\s*(png|webp|jpg|jpeg|bmp)", text, flags=re.IGNORECASE)
        if explicit_format:
            fmt = explicit_format.group(1).lower()
            parsed["target_format"] = "jpg" if fmt == "jpeg" else fmt
        else:
            format_match = None
            for fmt in ["png", "webp", "jpg", "jpeg", "bmp"]:
                if re.search(rf"\b{fmt}\b", text, flags=re.IGNORECASE):
                    format_match = fmt
            if format_match:
                parsed["target_format"] = "jpg" if format_match == "jpeg" else format_match

        dims = re.findall(r"(\d{2,5})\s*[x×*]\s*(\d{2,5})", text)
        if dims:
            width_str, height_str = dims[-1]
            parsed["width"] = int(width_str)
            parsed["height"] = int(height_str)

        width_match = re.search(r"(?:宽度不超过|宽不超过|最大宽度|宽度为|宽度设为|宽\s*[:：])\s*(\d{2,5})", text)
        if width_match:
            parsed["width"] = int(width_match.group(1))
            parsed["keep_ratio"] = True

        height_match = re.search(r"(?:高度不超过|高不超过|最大高度|高度为|高度设为|高\s*[:：])\s*(\d{2,5})", text)
        if height_match:
            parsed["height"] = int(height_match.group(1))
            parsed["keep_ratio"] = True

        if any(keyword in text for keyword in ["保持宽高比", "保持比例", "等比", "按比例", "智能调整", "缩放到不超过"]):
            parsed["keep_ratio"] = True

        if any(keyword in text for keyword in ["覆盖同名", "覆盖现有", "直接覆盖", "覆盖文件"]):
            parsed["overwrite"] = True
        if any(keyword in text for keyword in ["不覆盖", "不要覆盖", "跳过同名", "保留原文件"]):
            parsed["overwrite"] = False

        if any(keyword in text for keyword in ["允许有损", "确认有损", "接受有损", "有损转换"]):
            parsed["confirm_lossy"] = True

        start_match = re.search(r"(?:从|起始序号|序号从)\s*(\d{1,5})", text)
        if start_match:
            parsed["start_index"] = int(start_match.group(1))

        pad_match = re.search(r"(?:补零|填充宽度|位数|宽度)\s*(\d{1,2})", text)
        if pad_match:
            parsed["pad_width"] = int(pad_match.group(1))
        explicit_width = re.search(r"(\d{1,2})位", text)
        if explicit_width:
            parsed["pad_width"] = int(explicit_width.group(1))

        name_match = re.search(
            r"(?:重命名为|命名为|命名格式为)\s*([A-Za-z0-9_\-]+?)(0+\d+)\.(png|jpg|jpeg|webp|bmp)",
            text,
            flags=re.IGNORECASE,
        )
        if name_match:
            prefix = name_match.group(1)
            zero_part = name_match.group(2)
            parsed["pattern"] = f"{prefix}{{index}}"
            parsed["pad_width"] = len(zero_part)
            parsed["target_format"] = "jpg" if name_match.group(3).lower() == "jpeg" else name_match.group(3).lower()
        elif "序号" in text and "img" in text and "pattern" not in parsed:
            parsed["pattern"] = "img_{index}"

        return parsed

    def _process_single_image(
        self,
        src: Path,
        dst: Path,
        width: int,
        height: int,
        keep_ratio: bool,
        target_format: str,
        timeout_sec: float,
    ) -> None:
        """处理单张图片并应用超时限制。"""
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                self._process_single_image_impl,
                src,
                dst,
                width,
                height,
                keep_ratio,
                target_format,
            )
            try:
                future.result(timeout=max(timeout_sec, 0.1))
            except FuturesTimeoutError as exc:
                raise TimeoutError(str(exc)) from exc

    def _process_single_image_impl(
        self,
        src: Path,
        dst: Path,
        width: int,
        height: int,
        keep_ratio: bool,
        target_format: str,
    ) -> None:
        """处理单图核心逻辑。"""
        with Image.open(src) as img:
            if keep_ratio:
                img.thumbnail((width, height))
                processed = img
            else:
                processed = img.resize((width, height))
            processed.save(dst, format=target_format.upper())

    def _ensure_disk_space(self, files: list[Path]) -> None:
        total_size = sum(p.stat().st_size for p in files)
        estimated_need = int(total_size * 1.5)
        free = shutil.disk_usage(self.workspace_dir).free
        if free < estimated_need:
            raise ValueError(f"磁盘空间不足：预计需要 {estimated_need} 字节，可用 {free} 字节")
