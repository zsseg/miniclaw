from pathlib import Path

from clawmini.tools.writing_tool import WritingTool


def test_writing_tool_create_preview_commit_undo(tmp_path: Path) -> None:
    tool = WritingTool(workspace_dir=tmp_path)

    created = tool.run(
        {
            "command": "create",
            "topic": "人工智能伦理",
            "filename": "ethics.md",
            "word_count": 200,
        }
    )
    assert created.success

    target = tmp_path / "ethics.md"
    assert target.exists()

    preview = tool.run(
        {
            "command": "preview_edit",
            "file_path": str(target),
            "instruction": "把建议替换为建议方案",
        }
    )
    assert preview.success

    commit = tool.run({"command": "commit_edit", "file_path": str(target)})
    assert commit.success

    undo = tool.run({"command": "undo", "file_path": str(target)})
    assert undo.success


def test_writing_tool_default_filename_uses_txt(tmp_path: Path) -> None:
    tool = WritingTool(workspace_dir=tmp_path)

    created = tool.run(
        {
            "command": "create",
            "topic": "默认后缀测试",
            "word_count": 120,
        }
    )
    assert created.success
    path = Path(created.meta["file_path"])
    assert path.suffix == ".txt"
    assert path.exists()


def test_writing_tool_preview_edit_section(tmp_path: Path) -> None:
    tool = WritingTool(workspace_dir=tmp_path)
    target = tmp_path / "section.md"
    target.write_text("# 标题\n\n第一段建议\n\n第二段内容", encoding="utf-8")

    preview = tool.run(
        {
            "command": "preview_edit_section",
            "file_path": str(target),
            "section_index": 2,
            "instruction": "把建议替换为建议方案",
        }
    )
    assert preview.success

    commit = tool.run({"command": "commit_edit", "file_path": str(target)})
    assert commit.success
    assert "建议方案" in target.read_text(encoding="utf-8")


def test_writing_tool_preview_edit_makes_substantive_change(tmp_path: Path) -> None:
    tool = WritingTool(workspace_dir=tmp_path)
    target = tmp_path / "rewrite.md"
    original = "# 标题\n\n第一段说明观点。\n\n第二段展开分析。\n\n第三段给出结论。"
    target.write_text(original, encoding="utf-8")

    preview = tool.run(
        {
            "command": "preview_edit",
            "file_path": str(target),
            "instruction": "把第三段语气改得更正式，并补充结论的依据",
        }
    )
    assert preview.success

    commit = tool.run({"command": "commit_edit", "file_path": str(target)})
    assert commit.success
    updated = target.read_text(encoding="utf-8")
    assert updated != original
    assert "正式" in updated or "依据" in updated


def test_writing_tool_batch_create_and_status(tmp_path: Path) -> None:
    tool = WritingTool(workspace_dir=tmp_path)
    result = tool.run(
        {
            "command": "create_batch",
            "topics": ["主题A", "主题B", "主题C"],
            "word_count": 120,
            "output_dir": "batch_out",
            "ext": ".md",
        }
    )
    assert result.success
    job_id = result.meta.get("job_id")
    assert isinstance(job_id, str)

    status = tool.run({"command": "batch_status", "job_id": job_id})
    assert status.success
    assert status.meta["processed"] == 3
    assert status.meta["status"] == "completed"


def test_writing_tool_brainstorm_plans_open_request(tmp_path: Path) -> None:
    tool = WritingTool(workspace_dir=tmp_path)
    result = tool.run(
        {
            "command": "brainstorm_plans",
            "request": "帮我写一篇关于人工智能伦理的短文",
            "plan_count": 3,
        }
    )
    assert result.success
    plans = result.meta.get("plans", [])
    assert isinstance(plans, list)
    assert 2 <= len(plans) <= 3
    assert "方案1" in result.output


def test_writing_tool_brainstorm_plan_count_bounded(tmp_path: Path) -> None:
    tool = WritingTool(workspace_dir=tmp_path)
    low = tool.run({"command": "brainstorm_plans", "request": "写篇短文", "plan_count": 1})
    high = tool.run({"command": "brainstorm_plans", "request": "写篇短文", "plan_count": 10})
    assert low.success and high.success
    assert low.meta["count"] == 2
    assert high.meta["count"] == 3


def test_writing_tool_task_switch_and_status(tmp_path: Path) -> None:
    tool = WritingTool(workspace_dir=tmp_path)
    first = tool.run(
        {
            "command": "create",
            "topic": "任务A",
            "filename": "a.md",
            "task_id": "task_a",
        }
    )
    second = tool.run(
        {
            "command": "create",
            "topic": "任务B",
            "filename": "b.md",
            "task_id": "task_b",
        }
    )
    assert first.success and second.success

    switch = tool.run({"command": "switch_task", "task_id": "task_a"})
    assert switch.success

    status = tool.run({"command": "task_status"})
    assert status.success
    assert status.meta["task_id"] == "task_a"

    listed = tool.run({"command": "list_tasks"})
    assert listed.success
    assert len(listed.meta["tasks"]) >= 2


def test_writing_tool_preview_sanitizes_risky_content(tmp_path: Path) -> None:
    tool = WritingTool(workspace_dir=tmp_path)
    target = tmp_path / "risk.md"
    target.write_text("建议你先检查输入", encoding="utf-8")

    preview = tool.run(
        {
            "command": "preview_edit",
            "file_path": str(target),
            "instruction": "把建议替换为<script>alert(1)</script>",
        }
    )
    assert preview.success

    commit = tool.run({"command": "commit_edit", "file_path": str(target)})
    assert commit.success
    text = target.read_text(encoding="utf-8")
    assert "<script" not in text.lower()
    assert "已移除风险片段" in text


def test_writing_tool_create_with_custom_prompt_and_filename_normalization(tmp_path: Path) -> None:
    tool = WritingTool(workspace_dir=tmp_path)
    result = tool.run(
        {
            "command": "create",
            "topic": "AI治理",
            "style": "学术正式",
            "word_count": 300,
            "filename": "governance",  # 无扩展名
            "custom_prompt": "请强调风险治理与可审计性",
            "output_dir": "docs",
        }
    )
    assert result.success
    path = Path(result.meta["file_path"])
    assert path.name.endswith(".txt")
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "风险治理与可审计性" in text


def test_writing_tool_support_doc_extension(tmp_path: Path) -> None:
    tool = WritingTool(workspace_dir=tmp_path)
    result = tool.run(
        {
            "command": "create",
            "topic": "文档格式测试",
            "filename": "report.doc",
            "custom_prompt": "输出为普通文本内容即可",
        }
    )
    assert result.success
    path = Path(result.meta["file_path"])
    assert path.suffix == ".doc"
    assert path.exists()


def test_writing_tool_preview_plan_content(tmp_path: Path) -> None:
    tool = WritingTool(workspace_dir=tmp_path)
    preview = tool.run(
        {
            "command": "preview_plan_content",
            "topic": "人工智能伦理",
            "style": "通俗科普",
            "word_count": 400,
            "custom_prompt": "举一个校园场景案例",
        }
    )
    assert preview.success
    content = str(preview.meta.get("content", ""))
    assert "人工智能伦理" in content
    assert "校园场景案例" in content


def test_writing_tool_create_uses_external_api_when_configured(tmp_path: Path) -> None:
    tool = WritingTool(workspace_dir=tmp_path)

    def _fake_external(**kwargs: object) -> str:  # noqa: ANN003
        _ = kwargs
        return "# 外部API文稿\n\n这是来自外部API的正文。"

    tool._generate_article_via_api = _fake_external  # type: ignore[assignment]

    result = tool.run(
        {
            "command": "create",
            "topic": "外部生成测试",
            "api_provider": "deepseek",
            "api_key": "dummy-key",
            "api_model": "deepseek-chat",
            "filename": "external.md",
        }
    )
    assert result.success
    text = Path(result.meta["file_path"]).read_text(encoding="utf-8")
    assert "来自外部API" in text
