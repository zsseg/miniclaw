import time
from pathlib import Path

from PIL import Image  # type: ignore[import-not-found]

from clawmini.tools.image_batch_tool import ImageBatchTool


def _make_image(path: Path, size: tuple[int, int] = (64, 64)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", size, color=(100, 120, 130))
    img.save(path)


def test_image_tool_process_and_status(tmp_path: Path) -> None:
    _make_image(tmp_path / "images" / "a.jpg")
    _make_image(tmp_path / "images" / "b.jpg")

    tool = ImageBatchTool(workspace_dir=tmp_path)
    result = tool.run(
        {
            "command": "process",
            "task_id": "t001",
            "input_dir": "images",
            "output_dir": "output",
            "target_format": "png",
            "width": 32,
            "height": 32,
        }
    )
    assert result.success
    assert result.meta["task_id"] == "t001"

    status = tool.run({"command": "task_status", "task_id": "t001"})
    assert status.success
    assert status.meta["status"] in {"completed", "canceled"}
    assert status.meta["processed"] == status.meta["total"]


def test_image_tool_cancel_task(tmp_path: Path) -> None:
    tool = ImageBatchTool(workspace_dir=tmp_path)
    cancel = tool.run({"command": "cancel_task", "task_id": "t_cancel"})
    assert cancel.success
    assert "标记取消" in cancel.output


def test_image_tool_gif_to_png_requires_confirm(tmp_path: Path) -> None:
    gif_path = tmp_path / "images" / "anim.gif"
    gif_path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (32, 32), color=(200, 20, 20))
    img.save(gif_path, format="GIF")

    tool = ImageBatchTool(workspace_dir=tmp_path)
    denied = tool.run(
        {
            "command": "process",
            "task_id": "gif_no_confirm",
            "input_dir": "images",
            "output_dir": "out",
            "target_format": "png",
        }
    )
    assert not denied.success
    assert "confirm_lossy=true" in denied.output

    allowed = tool.run(
        {
            "command": "process",
            "task_id": "gif_confirmed",
            "input_dir": "images",
            "output_dir": "out2",
            "target_format": "png",
            "confirm_lossy": True,
        }
    )
    assert allowed.success


def test_image_tool_single_image_timeout(tmp_path: Path) -> None:
    _make_image(tmp_path / "images" / "slow.jpg")
    tool = ImageBatchTool(workspace_dir=tmp_path)

    original_impl = tool._process_single_image_impl

    def _slow_impl(
        src: Path,
        dst: Path,
        width: int,
        height: int,
        keep_ratio: bool,
        target_format: str,
    ) -> None:
        time.sleep(0.2)
        original_impl(src, dst, width, height, keep_ratio, target_format)

    tool._process_single_image_impl = _slow_impl  # type: ignore[assignment]

    result = tool.run(
        {
            "command": "process",
            "task_id": "timeout_case",
            "input_dir": "images",
            "output_dir": "out",
            "target_format": "png",
            "per_image_timeout_sec": 0.05,
        }
    )
    assert result.success
    assert any("超时" in item for item in result.meta["failed"])


def test_image_tool_pattern_and_overwrite(tmp_path: Path) -> None:
    _make_image(tmp_path / "images" / "first.jpg")
    _make_image(tmp_path / "images" / "second.jpg")
    tool = ImageBatchTool(workspace_dir=tmp_path)

    existing = tmp_path / "output" / "img_01.png"
    existing.parent.mkdir(parents=True, exist_ok=True)
    existing.write_bytes(b"keep-me")

    blocked = tool.run(
        {
            "command": "process",
            "task_id": "pattern_blocked",
            "input_dir": "images",
            "output_dir": "output",
            "target_format": "png",
            "pattern": "img_{index}",
            "start_index": 1,
            "pad_width": 2,
            "overwrite": False,
        }
    )
    assert blocked.success
    assert any("目标已存在" in item for item in blocked.meta["failed"])
    assert existing.read_bytes() == b"keep-me"

    allowed = tool.run(
        {
            "command": "process",
            "task_id": "pattern_allowed",
            "input_dir": "images",
            "output_dir": "output2",
            "target_format": "png",
            "pattern": "img_{index}",
            "start_index": 1,
            "pad_width": 2,
            "overwrite": True,
        }
    )
    assert allowed.success
    assert (tmp_path / "output2" / "img_01.png").exists()
    assert (tmp_path / "output2" / "img_02.png").exists()


def test_image_tool_keep_ratio_resizes_within_bounds(tmp_path: Path) -> None:
    _make_image(tmp_path / "images" / "wide.jpg", size=(80, 40))
    tool = ImageBatchTool(workspace_dir=tmp_path)

    result = tool.run(
        {
            "command": "process",
            "task_id": "keep_ratio",
            "input_dir": "images",
            "output_dir": "ratio_out",
            "target_format": "png",
            "width": 50,
            "height": 50,
            "keep_ratio": True,
            "overwrite": True,
        }
    )
    assert result.success
    out = tmp_path / "ratio_out" / "img_001.png"
    assert out.exists()
    with Image.open(out) as img:
        assert img.size == (50, 25)


def test_image_tool_natural_language_request(tmp_path: Path) -> None:
    _make_image(tmp_path / "source" / "one.jpg", size=(80, 40))
    _make_image(tmp_path / "source" / "two.jpg", size=(80, 40))
    tool = ImageBatchTool(workspace_dir=tmp_path)

    result = tool.run(
        {
            "command": "process",
            "task_id": "nl_request",
            "request": "从 source 文件夹中把所有 JPEG 图片调整为 32x16，转换为 PNG，重命名为 img_001.png，保存到 out/，保持宽高比，不覆盖同名文件",
        }
    )
    assert result.success
    assert (tmp_path / "out" / "img_001.png").exists()
    assert (tmp_path / "out" / "img_002.png").exists()
    with Image.open(tmp_path / "out" / "img_001.png") as img:
        assert img.size == (32, 16)
