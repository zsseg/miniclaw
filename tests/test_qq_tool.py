import json
from email.message import Message
from io import BytesIO
import urllib.error
import sys
import types
from pathlib import Path
from typing import Any

from app import _QQWebhookRequestHandler
from clawmini.adapters.qq_adapter import QQClientBinding, WindowsQQGateway, build_gateway_event, discover_napcat_http_config
from clawmini.tools import qq_auto_reply as qq_auto_reply_module
from clawmini.tools.qq_auto_reply import QQAutoReplyTool


def test_qq_tool_switch_gateway_fallback(tmp_path: Path) -> None:
    tool = QQAutoReplyTool(workspace_dir=tmp_path)

    ok = tool.run({"command": "set_gateway", "mode": "mock"})
    assert ok.success
    assert tool.gateway_mode == "mock"

    windows = tool.run({"command": "set_gateway", "mode": "windows"})
    assert windows.success
    assert tool.gateway_mode == "windows"
    if isinstance(windows.meta.get("binding"), dict):
        assert windows.meta["binding"]["notes"]
        assert "pywinauto" in windows.output or "pywinauto" in windows.meta["binding"]["notes"]


def test_qq_tool_defaults_to_managed_and_zero_delays(tmp_path: Path) -> None:
    tool = QQAutoReplyTool(workspace_dir=tmp_path)

    status = tool.run({"command": "get_status"})

    assert status.success
    assert tool.gateway_mode == "managed"
    assert tool.private_delay_sec == 0
    assert tool.cooldown_sec == 0
    assert "token=未配置" in status.output


def test_qq_tool_switch_gateway_managed(tmp_path: Path) -> None:
    tool = QQAutoReplyTool(workspace_dir=tmp_path)
    result = tool.run({"command": "set_gateway", "mode": "managed", "managed_account": "10001"})

    assert result.success
    assert tool.gateway_mode == "managed"
    assert isinstance(result.meta.get("binding"), dict)
    assert result.meta["binding"]["connected"] is True
    assert "托管账号" in result.meta["binding"]["notes"]


def test_qq_tool_managed_gateway_sends_group_msg_via_napcat(tmp_path: Path, monkeypatch) -> None:
    tool = QQAutoReplyTool(workspace_dir=tmp_path)
    configured = tool.run(
        {
            "command": "configure",
            "target_group_id": "1058712846",
            "self_user_id": "3892874358",
            "gateway_mode": "managed",
            "managed_account": "3892874358",
            "managed_api_base_url": "http://127.0.0.1:6099/plugin/napcat-plugin-builtin/api",
            "managed_access_token": "",
        }
    )
    assert configured.success

    calls: list[dict[str, object]] = []

    class FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b'{"status":"ok"}'

    def fake_urlopen(req, timeout=30):
        calls.append({"url": req.full_url, "headers": dict(req.headers), "body": req.data.decode("utf-8") if req.data else "", "timeout": timeout})
        return FakeResp()

    monkeypatch.setattr("clawmini.adapters.qq_adapter.urllib.request.urlopen", fake_urlopen)

    result = tool.run(
        {
            "command": "handle_message",
            "source": "group",
            "chat_id": "1058712846",
            "sender_id": "u_sender",
            "text": "@me 你好，请发一条回复",
            "mentioned": True,
            "mention_all": False,
        }
    )

    assert result.success
    assert result.meta["endpoint"] == "http://127.0.0.1:6099/plugin/napcat-plugin-builtin/api/send_group_msg"
    assert result.meta["response"] == '{"status":"ok"}'
    assert calls
    assert calls[0]["url"] == "http://127.0.0.1:6099/plugin/napcat-plugin-builtin/api/send_group_msg"
    assert '"group_id": 1058712846' in str(calls[0]["body"])
    assert '"message":' in str(calls[0]["body"])


def test_qq_tool_managed_gateway_reports_unauthorized_as_failure(tmp_path: Path, monkeypatch) -> None:
    tool = QQAutoReplyTool(workspace_dir=tmp_path)
    configured = tool.run(
        {
            "command": "configure",
            "target_group_id": "1058712846",
            "self_user_id": "3892874358",
            "gateway_mode": "managed",
            "managed_account": "3892874358",
            "managed_api_base_url": "http://127.0.0.1:6099/plugin/napcat-plugin-builtin/api",
            "managed_access_token": "bad-token",
        }
    )
    assert configured.success

    class FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b'{"code":-1,"message":"Unauthorized"}'

    monkeypatch.setattr("clawmini.adapters.qq_adapter.urllib.request.urlopen", lambda req, timeout=30: FakeResp())

    result = tool.run(
        {
            "command": "handle_message",
            "source": "group",
            "chat_id": "1058712846",
            "sender_id": "u_sender",
            "text": "@me 你好，请发一条回复",
            "mentioned": True,
            "mention_all": False,
        }
    )

    assert result.success is False
    assert "Unauthorized" in result.output
    assert result.meta["reason"] == "unauthorized"


def test_qq_tool_managed_gateway_falls_back_when_first_endpoint_is_not_found(tmp_path: Path, monkeypatch) -> None:
    tool = QQAutoReplyTool(workspace_dir=tmp_path)
    configured = tool.run(
        {
            "command": "configure",
            "target_group_id": "1058712846",
            "self_user_id": "3892874358",
            "gateway_mode": "managed",
            "managed_account": "3892874358",
            "managed_api_base_url": "http://127.0.0.1:6099/plugin/napcat-plugin-builtin/api",
            "managed_access_token": "",
        }
    )
    assert configured.success

    calls: list[str] = []

    class FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b'{"status":"ok"}'

    def fake_urlopen(req, timeout=30):
        calls.append(req.full_url)
        if len(calls) == 1:
            raise urllib.error.HTTPError(req.full_url, 404, "Not Found", hdrs=Message(), fp=None)
        return FakeResp()

    monkeypatch.setattr("clawmini.adapters.qq_adapter.urllib.request.urlopen", fake_urlopen)

    result = tool.run(
        {
            "command": "handle_message",
            "source": "group",
            "chat_id": "1058712846",
            "sender_id": "u_sender",
            "text": "@me 你好，请发一条回复",
            "mentioned": True,
            "mention_all": False,
        }
    )

    assert result.success
    assert len(calls) >= 2
    assert calls[0] == "http://127.0.0.1:6099/plugin/napcat-plugin-builtin/api/send_group_msg"


def test_qq_tool_configure_persists_managed_fields(tmp_path: Path) -> None:
    tool = QQAutoReplyTool(workspace_dir=tmp_path)
    result = tool.run(
        {
            "command": "configure",
            "gateway_mode": "managed",
            "managed_account": "3892874358",
            "managed_api_base_url": "http://127.0.0.1:6099/plugin/napcat-plugin-builtin/api",
            "managed_access_token": "secret-token",
        }
    )

    assert result.success
    assert result.meta["managed_account"] == "3892874358"
    assert result.meta["managed_api_base_url"] == "http://127.0.0.1:6099/plugin/napcat-plugin-builtin/api"
    assert result.meta["managed_access_token"] == "secret-token"
    assert "Token已更新成功" in result.output

    reloaded = QQAutoReplyTool(workspace_dir=tmp_path)
    status = reloaded.run({"command": "get_status"})
    assert status.success
    assert reloaded.gateway_mode == "managed"
    assert reloaded.managed_account == "3892874358"
    assert reloaded.managed_api_base_url == "http://127.0.0.1:6099/plugin/napcat-plugin-builtin/api"
    assert reloaded.managed_access_token == "secret-token"


def test_qq_tool_private_enabled_false_persists_and_reports(tmp_path: Path) -> None:
    tool = QQAutoReplyTool(workspace_dir=tmp_path)
    result = tool.run(
        {
            "command": "configure",
            "private_enabled": False,
            "target_group_id": "g001",
        }
    )

    assert result.success
    assert tool.private_enabled is False
    status = tool.run({"command": "get_status"})
    assert status.success
    assert status.meta["private_enabled"] is False


def test_discover_napcat_http_config_from_local_install(tmp_path: Path) -> None:
    config_dir = tmp_path / "NapCat.Shell.Windows.OneKey" / "NapCat.44498.Shell" / "versions" / "9.9.26-44498" / "resources" / "app" / "napcat" / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "webui.json").write_text('{"port":6099,"token":"webui-token"}', encoding="utf-8")
    (config_dir / "onebot11_3892874358.json").write_text('{"network":{"httpServers":[{"enable":true,"host":"127.0.0.1","port":3000,"token":"http-token"}]}}', encoding="utf-8")

    result = discover_napcat_http_config([tmp_path])

    assert result is not None
    assert result["account_id"] == "3892874358"
    assert result["api_base_url"] == "http://127.0.0.1:3000/plugin/napcat-plugin-builtin/api"
    assert result["access_token"] == "http-token"
    assert result["webui_token"] == "webui-token"


def test_discover_napcat_http_config_reads_http_client_token_separately(tmp_path: Path) -> None:
    config_dir = tmp_path / "NapCat.Shell.Windows.OneKey" / "NapCat.44498.Shell" / "versions" / "9.9.26-44498" / "resources" / "app" / "napcat" / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "webui.json").write_text('{"port":6099,"token":"webui-token"}', encoding="utf-8")
    (config_dir / "onebot11_3892874358.json").write_text('{"network":{"httpClients":[{"token":"client-token"}]}}', encoding="utf-8")

    result = discover_napcat_http_config([tmp_path])

    assert result is not None
    assert result["account_id"] == "3892874358"
    assert result["access_token"] == ""
    assert result["client_token"] == "client-token"
    assert result["webui_token"] == "webui-token"


def test_discover_napcat_http_config_reads_event_post_url(tmp_path: Path) -> None:
    config_dir = tmp_path / "NapCat.Shell.Windows.OneKey" / "NapCat.44498.Shell" / "versions" / "9.9.26-44498" / "resources" / "app" / "napcat" / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "webui.json").write_text('{"port":6099,"token":"webui-token"}', encoding="utf-8")
    (config_dir / "onebot11_3892874358.json").write_text(
        '{"network":{"httpServers":[{"enable":true,"host":"127.0.0.1","port":3000,"token":"http-token"}],"httpClients":[{"enable":true,"url":"http://127.0.0.1:17888/qq/event","token":"client-token"}]}}',
        encoding="utf-8",
    )

    result = discover_napcat_http_config([tmp_path])

    assert result is not None
    assert result["api_base_url"] == "http://127.0.0.1:3000/plugin/napcat-plugin-builtin/api"
    assert result["event_post_url"] == "http://127.0.0.1:17888/qq/event"


def test_windows_gateway_sends_via_napcat_when_configured(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    class FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b'{"status":"ok"}'

    def fake_urlopen(req, timeout=30):
        calls.append({"url": req.full_url, "body": req.data.decode("utf-8") if req.data else "", "timeout": timeout})
        return FakeResp()

    monkeypatch.setattr(WindowsQQGateway, "_check_dependency", lambda self: True)
    monkeypatch.setattr("clawmini.adapters.qq_adapter.urllib.request.urlopen", fake_urlopen)

    gateway = WindowsQQGateway(api_base_url="http://127.0.0.1:6099/plugin/napcat-plugin-builtin/api")
    gateway.send_text("1058712846", "你好，来自 Windows 网关", "group")

    assert calls
    assert calls[0]["url"] == "http://127.0.0.1:6099/plugin/napcat-plugin-builtin/api/send_group_msg"
    assert '"group_id": 1058712846' in str(calls[0]["body"])


def test_qq_tool_bootstrap_autofills_napcat_fields(tmp_path: Path) -> None:
    config_dir = tmp_path / "NapCat.Shell.Windows.OneKey" / "NapCat.44498.Shell" / "versions" / "9.9.26-44498" / "resources" / "app" / "napcat" / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "webui.json").write_text('{"port":6099,"token":"webui-token"}', encoding="utf-8")
    (config_dir / "onebot11_3892874358.json").write_text('{"network":{"httpServers":[{"enable":true,"host":"127.0.0.1","port":3000,"token":"http-token"}]}}', encoding="utf-8")

    tool = QQAutoReplyTool(workspace_dir=tmp_path)
    result = tool.run(
        {
            "command": "bootstrap",
            "gateway_mode": "windows",
            "search_roots": [str(tmp_path)],
            "connect_now": False,
        }
    )

    assert result.success
    assert tool.gateway_mode == "windows"
    assert tool.managed_account == "3892874358"
    assert tool.managed_api_base_url == "http://127.0.0.1:3000/plugin/napcat-plugin-builtin/api"
    assert tool.managed_access_token == "http-token"


def test_qq_tool_download_napcat_opens_release_page(tmp_path: Path, monkeypatch) -> None:
    opened: list[str] = []

    def fake_open_new_tab(url: str) -> bool:
        opened.append(url)
        return True

    monkeypatch.setattr("clawmini.tools.qq_auto_reply.webbrowser.open_new_tab", fake_open_new_tab)

    tool = QQAutoReplyTool(workspace_dir=tmp_path)
    result = tool.run({"command": "download_napcat"})

    assert result.success
    assert opened == ["https://github.com/NapNeko/NapCatQQ/releases/latest"]
    assert result.meta["url"] == "https://github.com/NapNeko/NapCatQQ/releases/latest"


def test_qq_tool_configure_with_gateway_mode(tmp_path: Path) -> None:
    tool = QQAutoReplyTool(workspace_dir=tmp_path)

    result = tool.run({
        "command": "configure",
        "enabled": True,
        "private_enabled": True,
        "target_group_id": "g123",
        "private_delay_sec": 45,
        "custom_prompt": "简洁回答",
        "cooldown_sec": 12,
        "self_user_id": "self_001",
        "gateway_mode": "mock",
    })
    assert result.success
    assert tool.target_group_id == "g123"
    assert tool.private_delay_sec == 45
    assert tool.custom_prompt == "简洁回答"
    assert tool.cooldown_sec == 12
    assert tool.self_user_id == "self_001"
    assert tool.gateway_mode == "mock"
    assert result.meta["target_group_id"] == "g123"
    assert result.meta["cooldown_sec"] == 12
    assert result.meta["self_user_id"] == "self_001"


def test_qq_tool_configure_persists_reply_api_fields(tmp_path: Path) -> None:
    tool = QQAutoReplyTool(workspace_dir=tmp_path)
    result = tool.run(
        {
            "command": "configure",
            "reply_api_provider": "deepseek",
            "reply_api_model": "deepseek-chat",
            "reply_api_key": "secret",
            "reply_api_base_url": "https://api.deepseek.com/v1",
        }
    )

    assert result.success
    assert result.meta["reply_api_provider"] == "deepseek"
    assert result.meta["reply_api_model"] == "deepseek-chat"
    assert result.meta["reply_api_key"] == "secret"
    assert result.meta["reply_api_base_url"] == "https://api.deepseek.com"


def test_qq_tool_status_and_pending_flow(tmp_path: Path) -> None:
    tool = QQAutoReplyTool(workspace_dir=tmp_path)

    status = tool.run({"command": "get_status"})
    assert status.success
    assert "pending_private" in status.output
    assert status.meta["pending_private_items"] == []

    queued = tool.run(
        {
            "command": "handle_message",
            "source": "private",
            "chat_id": "u001",
            "sender_id": "s001",
            "text": "你好",
            "waited_sec": 0,
        }
    )
    assert queued.success
    assert "进入等待队列" in queued.output

    canceled = tool.run({"command": "user_replied", "chat_id": "u001"})
    assert canceled.success

    poll = tool.run({"command": "poll_pending"})
    assert poll.success
    assert "pending轮询完成" in poll.output


def test_qq_tool_group_mention_all_is_ignored(tmp_path: Path) -> None:
    tool = QQAutoReplyTool(workspace_dir=tmp_path)
    tool.run({"command": "configure", "target_group_id": "g001"})

    result = tool.run(
        {
            "command": "handle_message",
            "source": "group",
            "chat_id": "g001",
            "sender_id": "u_sender",
            "text": "@所有人 今天开会",
            "mentioned": True,
            "mention_all": True,
        }
    )

    assert result.success
    assert "不触发自动回复" in result.output


def test_qq_tool_multiple_target_groups_match(tmp_path: Path) -> None:
    tool = QQAutoReplyTool(workspace_dir=tmp_path)
    cfg = tool.run(
        {
            "command": "configure",
            "target_group_id": "1058712846, 20002",
            "self_user_id": "3892874358",
            "gateway_mode": "managed",
        }
    )
    assert cfg.success
    assert "1058712846" in cfg.meta["target_group_id"]
    assert cfg.meta["target_group_ids"] == ["1058712846", "20002"]

    result = tool.run(
        {
            "command": "handle_message",
            "source": "group",
            "chat_id": "1058712846",
            "sender_id": "u_sender",
            "text": "@me 测试多群命中",
            "mentioned": True,
            "mention_all": False,
        }
    )
    assert result.success
    assert "已自动回复" in result.output


def test_qq_tool_group_list_add_remove_update(tmp_path: Path) -> None:
    tool = QQAutoReplyTool(workspace_dir=tmp_path)
    tool.run({"command": "configure", "target_group_id": "10001"})

    add_result = tool.run({"command": "add_target_group", "group_id": "1058712846"})
    assert add_result.success
    assert "1058712846" in add_result.meta["target_group_ids"]

    update_result = tool.run({"command": "update_target_group", "old_group_id": "10001", "new_group_id": "20002"})
    assert update_result.success
    assert "20002" in update_result.meta["target_group_ids"]
    assert "10001" not in update_result.meta["target_group_ids"]

    remove_result = tool.run({"command": "remove_target_group", "group_id": "20002"})
    assert remove_result.success
    assert "20002" not in remove_result.meta["target_group_ids"]


def test_qq_tool_handle_message_reports_reply(tmp_path: Path) -> None:
    tool = QQAutoReplyTool(workspace_dir=tmp_path)
    tool.run({"command": "configure", "target_group_id": "g001", "self_user_id": "me"})

    result = tool.run(
        {
            "command": "handle_message",
            "source": "group",
            "chat_id": "g001",
            "sender_id": "u_sender",
            "text": "@me 你好，帮我看一下",
            "mentioned": True,
            "mention_all": False,
        }
    )

    assert result.success
    assert "已自动回复" in result.output


def test_qq_tool_windows_send_not_implemented_returns_hint(tmp_path: Path, monkeypatch) -> None:
    tool = QQAutoReplyTool(workspace_dir=tmp_path)
    tool.run({"command": "configure", "target_group_id": "g001", "gateway_mode": "windows"})

    class FakeGateway:
        def send_text(self, chat_id: str, text: str, message_type: str = "group") -> None:
            _ = message_type
            _ = chat_id, text
            raise NotImplementedError("WindowsQQGateway.send_text 尚未完成真实 UI 自动化步骤。")

        def bind_local_client(self, app_title_keyword="QQ", process_name="", executable_path="", window_title="", connect_now=True):
            _ = process_name, executable_path, window_title, connect_now
            return QQClientBinding(app_title_keyword=app_title_keyword)

        def auto_bind_local_client(self, connect_now=True, search_roots=None):
            _ = connect_now, search_roots
            return QQClientBinding(app_title_keyword="QQ")

    tool.gateway = FakeGateway()
    result = tool.run(
        {
            "command": "handle_message",
            "source": "group",
            "chat_id": "g001",
            "sender_id": "u_sender",
            "text": "@me 你好，帮我看一下",
            "mentioned": True,
            "mention_all": False,
        }
    )

    assert not result.success
    assert "managed" in result.output


def test_qq_tool_private_message_queue_feedback(tmp_path: Path) -> None:
    tool = QQAutoReplyTool(workspace_dir=tmp_path)
    tool.run({"command": "configure", "private_delay_sec": 60, "private_enabled": True})

    result = tool.run(
        {
            "command": "handle_message",
            "source": "private",
            "chat_id": "u001",
            "sender_id": "s001",
            "text": "你好",
            "waited_sec": 0,
        }
    )

    assert result.success
    assert "进入等待队列" in result.output


def test_qq_tool_api_reply_is_used_when_configured(tmp_path: Path, monkeypatch) -> None:
    tool = QQAutoReplyTool(workspace_dir=tmp_path)
    tool.run(
        {
            "command": "configure",
            "target_group_id": "g001",
            "self_user_id": "me",
            "reply_api_provider": "deepseek",
            "reply_api_model": "deepseek-chat",
            "reply_api_key": "fake-key",
            "reply_api_base_url": "https://api.deepseek.com/v1",
        }
    )

    class FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps({"choices": [{"message": {"content": "好的，我来帮你处理。"}}]}).encode("utf-8")

    def fake_urlopen(req, timeout=60):
        _ = req, timeout
        return FakeResp()

    monkeypatch.setattr("clawmini.tools.qq_auto_reply.urllib.request.urlopen", fake_urlopen)

    result = tool.run(
        {
            "command": "handle_message",
            "source": "group",
            "chat_id": "g001",
            "sender_id": "u_sender",
            "text": "@me 你帮我回复一下",
            "mentioned": True,
            "mention_all": False,
        }
    )

    assert result.success
    assert "好的，我来帮你处理。" in result.output
    assert isinstance(result.meta, dict)
    assert result.meta.get("reply_source") == "deepseek"
    assert result.meta.get("reply_api_error") == ""


def test_qq_tool_sends_multiple_reply_segments(tmp_path: Path, monkeypatch) -> None:
    tool = QQAutoReplyTool(workspace_dir=tmp_path)
    tool.run(
        {
            "command": "configure",
            "target_group_id": "g001",
            "self_user_id": "me",
            "reply_api_provider": "deepseek",
            "reply_api_model": "deepseek-chat",
            "reply_api_key": "fake-key",
            "reply_api_base_url": "https://api.deepseek.com",
        }
    )

    sent_records: list[tuple[str, str, str]] = []

    def fake_send_via_gateway(chat_id, reply, message_type):
        sent_records.append((chat_id, reply, message_type))
        return qq_auto_reply_module.ToolResult(True, "ok", {"sent": reply})

    class FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps(
                {
                    "choices": [
                        {
                            "message": {
                                "content": "第一段回复。\n\n第二段回复。"
                            }
                        }
                    ]
                }
            ).encode("utf-8")

    def fake_urlopen(req, timeout=60):
        body = json.loads(req.data.decode("utf-8"))
        assert "如果需要多条回复" in body["messages"][0]["content"]
        return FakeResp()

    monkeypatch.setattr(tool, "_send_via_gateway", fake_send_via_gateway)
    monkeypatch.setattr("clawmini.tools.qq_auto_reply.urllib.request.urlopen", fake_urlopen)

    result = tool.run(
        {
            "command": "handle_message",
            "source": "group",
            "chat_id": "g001",
            "sender_id": "u_sender",
            "text": "@me 请分两点回答",
            "mentioned": True,
            "mention_all": False,
        }
    )

    assert result.success
    assert isinstance(result.meta, dict)
    assert result.meta.get("reply_count") == 2
    assert result.meta.get("reply_parts") == ["第一段回复。", "第二段回复。"]
    assert sent_records == [
        ("g001", "第一段回复。", "group"),
        ("g001", "第二段回复。", "group"),
    ]


def test_qq_tool_includes_group_context_in_prompt(tmp_path: Path, monkeypatch) -> None:
    tool = QQAutoReplyTool(workspace_dir=tmp_path)
    tool.run(
        {
            "command": "configure",
            "target_group_id": "g001",
            "self_user_id": "me",
            "reply_api_provider": "deepseek",
            "reply_api_model": "deepseek-chat",
            "reply_api_key": "fake-key",
            "reply_api_base_url": "https://api.deepseek.com",
        }
    )

    bodies: list[dict[str, Any]] = []

    class FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps({"choices": [{"message": {"content": "收到。"}}]}).encode("utf-8")

    def fake_urlopen(req, timeout=60):
        body = json.loads(req.data.decode("utf-8"))
        bodies.append(body)
        return FakeResp()

    def fake_send_via_gateway(chat_id, reply, message_type):
        _ = chat_id, reply, message_type
        return qq_auto_reply_module.ToolResult(True, "ok", {})

    monkeypatch.setattr(tool, "_send_via_gateway", fake_send_via_gateway)
    monkeypatch.setattr("clawmini.tools.qq_auto_reply.urllib.request.urlopen", fake_urlopen)

    first = tool.run(
        {
            "command": "handle_message",
            "source": "group",
            "chat_id": "g001",
            "sender_id": "u001",
            "sender_name": "小明",
            "group_name": "测试群",
            "group_avatar": "https://example.com/group.png",
            "text": "@me 第一轮内容",
            "mentioned": True,
            "mention_all": False,
        }
    )
    second = tool.run(
        {
            "command": "handle_message",
            "source": "group",
            "chat_id": "g001",
            "sender_id": "u002",
            "sender_name": "小红",
            "group_name": "测试群",
            "group_avatar": "https://example.com/group.png",
            "text": "@me 第二轮追问",
            "mentioned": True,
            "mention_all": False,
        }
    )

    assert first.success and second.success
    assert len(bodies) == 2
    second_body = bodies[1]
    prompt_content = str(second_body["messages"][0]["content"])
    assert "群聊场景：群名=测试群" in prompt_content
    assert "群头像=https://example.com/group.png" in prompt_content
    assert "最近对话：" in prompt_content
    assert "第一轮内容" in prompt_content
    assert "收到。" in str(second.output)


def test_qq_tool_prompt_avoids_avatar_visibility_claims(tmp_path: Path, monkeypatch) -> None:
    tool = QQAutoReplyTool(workspace_dir=tmp_path)
    tool.run(
        {
            "command": "configure",
            "target_group_id": "g001",
            "self_user_id": "me",
            "reply_api_provider": "deepseek",
            "reply_api_model": "deepseek-chat",
            "reply_api_key": "fake-key",
            "reply_api_base_url": "https://api.deepseek.com",
        }
    )

    captured: list[dict[str, Any]] = []

    class FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps({"choices": [{"message": {"content": "收到。"}}]}).encode("utf-8")

    def fake_urlopen(req, timeout=60):
        captured.append(json.loads(req.data.decode("utf-8")))
        return FakeResp()

    monkeypatch.setattr(tool, "_send_via_gateway", lambda chat_id, reply, message_type: qq_auto_reply_module.ToolResult(True, "ok", {}))
    monkeypatch.setattr("clawmini.tools.qq_auto_reply.urllib.request.urlopen", fake_urlopen)

    tool.run(
        {
            "command": "handle_message",
            "source": "group",
            "chat_id": "g001",
            "sender_id": "u001",
            "sender_name": "小明",
            "group_name": "🐷小兰爱好者群",
            "group_avatar": "https://example.com/avatar.png",
            "text": "头像是什么风格？",
            "mentioned": True,
            "mention_all": False,
        }
    )

    prompt_content = str(captured[0]["messages"][0]["content"])
    assert "不要说自己看不见群头像" in prompt_content
    assert "不要解释自己无法观察到这些内容" in prompt_content
    assert "🐷小兰爱好者群" in prompt_content


def test_qq_tool_uses_image_url_content_when_enabled(tmp_path: Path, monkeypatch) -> None:
    tool = QQAutoReplyTool(workspace_dir=tmp_path)
    tool.run(
        {
            "command": "configure",
            "target_group_id": "g001",
            "self_user_id": "me",
            "reply_api_provider": "deepseek",
            "reply_api_model": "deepseek-chat",
            "reply_api_key": "fake-key",
            "reply_api_base_url": "https://api.deepseek.com",
            "enable_image_recognition": True,
        }
    )

    bodies: list[dict[str, Any]] = []

    class FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps({"choices": [{"message": {"content": "收到。"}}]}).encode("utf-8")

    def fake_urlopen(req, timeout=60):
        bodies.append(json.loads(req.data.decode("utf-8")))
        return FakeResp()

    monkeypatch.setattr(tool, "_send_via_gateway", lambda chat_id, reply, message_type: qq_auto_reply_module.ToolResult(True, "ok", {}))
    monkeypatch.setattr("clawmini.tools.qq_auto_reply.urllib.request.urlopen", fake_urlopen)

    result = tool.run(
        {
            "command": "handle_message",
            "source": "group",
            "chat_id": "g001",
            "sender_id": "u001",
            "sender_name": "小明",
            "group_name": "测试群",
            "text": "帮我看看这张图",
            "mentioned": True,
            "mention_all": False,
            "image_refs": ["https://example.com/pic.png"],
        }
    )

    assert result.success
    user_content = bodies[0]["messages"][1]["content"]
    assert isinstance(user_content, list)
    assert user_content[0]["type"] == "text"
    assert user_content[1]["type"] == "image_url"
    assert user_content[1]["image_url"]["url"] == "https://example.com/pic.png"


def test_qq_tool_rejects_non_ascii_api_key(tmp_path: Path, monkeypatch) -> None:
    tool = QQAutoReplyTool(workspace_dir=tmp_path)
    tool.run(
        {
            "command": "configure",
            "target_group_id": "g001",
            "self_user_id": "me",
            "reply_api_provider": "deepseek",
            "reply_api_model": "deepseek-chat",
            "reply_api_key": "设置123",
            "reply_api_base_url": "https://api.deepseek.com",
        }
    )

    def fake_send_via_gateway(chat_id, reply, message_type):
        _ = chat_id, reply, message_type
        return qq_auto_reply_module.ToolResult(True, "ok", {})

    monkeypatch.setattr(tool, "_send_via_gateway", fake_send_via_gateway)

    result = tool.run(
        {
            "command": "handle_message",
            "source": "group",
            "chat_id": "g001",
            "sender_id": "u_sender",
            "text": "@me 你帮我回复一下",
            "mentioned": True,
            "mention_all": False,
        }
    )

    assert result.success
    assert isinstance(result.meta, dict)
    assert result.meta.get("reply_source") == "local"
    assert "非 ASCII 字符" in str(result.meta.get("reply_api_error", ""))


def test_gateway_event_detects_at_me(tmp_path: Path) -> None:
    _ = tmp_path
    event = build_gateway_event(
        {
            "source": "group",
            "chat_id": "g001",
            "sender_id": "u001",
            "text": "@me 帮看下",
            "mentions": ["me", "u002"],
            "mention_all": False,
        }
    )
    msg = event.to_message(self_user_id="me")
    assert msg.mentioned is True
    assert msg.mention_all is False

    all_event = build_gateway_event(
        {
            "source": "group",
            "chat_id": "g001",
            "sender_id": "u001",
            "text": "@所有人",
            "mentions": ["me"],
            "mention_all": True,
        }
    )
    all_msg = all_event.to_message(self_user_id="me")
    assert all_msg.mentioned is False
    assert all_msg.mention_all is True


def test_gateway_event_parses_raw_onebot_group_message(tmp_path: Path) -> None:
    _ = tmp_path
    event = build_gateway_event(
        {
            "post_type": "message",
            "message_type": "group",
            "group_id": 1058712846,
            "user_id": 3892874358,
            "sender": {"user_id": 3892874358},
            "message": [
                {"type": "at", "data": {"qq": "3892874358"}},
                {"type": "text", "data": {"text": " 你好，来一条回复"}},
            ],
        }
    )
    msg = event.to_message(self_user_id="3892874358")
    assert msg.source == "group"
    assert msg.chat_id == "1058712846"
    assert msg.sender_id == "3892874358"
    assert msg.text == "你好，来一条回复"
    assert msg.mentioned is True


def test_gateway_event_parses_image_refs(tmp_path: Path) -> None:
    _ = tmp_path
    event = build_gateway_event(
        {
            "post_type": "message",
            "message_type": "group",
            "group_id": 1058712846,
            "user_id": 3892874358,
            "sender": {"user_id": 3892874358},
            "message": [
                {"type": "image", "data": {"url": "https://example.com/pic.png"}},
                {"type": "text", "data": {"text": " 看看这个图"}},
            ],
        }
    )
    msg = event.to_message(self_user_id="3892874358")
    assert msg.source == "group"
    assert msg.text == "看看这个图"
    assert msg.image_refs == ["https://example.com/pic.png"]


def test_gateway_event_unwraps_payload_envelope(tmp_path: Path) -> None:
    _ = tmp_path
    event = build_gateway_event(
        {
            "payload": {
                "post_type": "message",
                "message_type": "private",
                "user_id": 3892874358,
                "sender": {"user_id": 3892874358},
                "raw_message": "收到",
            }
        }
    )
    msg = event.to_message(self_user_id="3892874358")
    assert msg.source == "private"
    assert msg.chat_id == "3892874358"
    assert msg.sender_id == "3892874358"
    assert msg.text == "收到"


def test_gateway_event_parses_type_detail_type_envelope(tmp_path: Path) -> None:
    _ = tmp_path
    event = build_gateway_event(
        {
            "type": "message",
            "detail_type": "group",
            "data": {
                "group_id": 1058712846,
                "user_id": 3892874358,
                "sender": {"user_id": 3892874358},
                "message": [
                    {"type": "text", "data": {"text": "收到"}},
                ],
            },
        }
    )
    msg = event.to_message(self_user_id="3892874358")
    assert msg.source == "group"
    assert msg.chat_id == "1058712846"
    assert msg.sender_id == "3892874358"
    assert msg.text == "收到"


def test_qq_tool_handle_gateway_event_and_persist_config(tmp_path: Path) -> None:
    tool = QQAutoReplyTool(workspace_dir=tmp_path)
    configured = tool.run(
        {
            "command": "configure",
            "target_group_id": "g001",
            "self_user_id": "me",
            "private_delay_sec": 20,
            "custom_prompt": "仅答复业务",
        }
    )
    assert configured.success

    ignored = tool.run(
        {
            "command": "handle_gateway_event",
            "event": {
                "source": "group",
                "chat_id": "g001",
                "sender_id": "u_sender",
                "text": "@u2 帮忙",
                "mentions": ["u2"],
                "mention_all": False,
            },
        }
    )
    assert ignored.success
    assert "未明确@我" in ignored.output

    triggered = tool.run(
        {
            "command": "handle_gateway_event",
            "event": {
                "source": "group",
                "chat_id": "g001",
                "sender_id": "u_sender",
                "text": "@me 帮我看一下",
                "mentions": ["me"],
                "mention_all": False,
            },
        }
    )
    assert triggered.success
    assert "已自动回复" in triggered.output

    # 验证配置持久化：重新实例化后可加载。
    reloaded = QQAutoReplyTool(workspace_dir=tmp_path)
    status = reloaded.run({"command": "get_status"})
    assert status.success
    assert reloaded.target_group_id == "g001"
    assert reloaded.private_delay_sec == 20
    assert reloaded.self_user_id == "me"


def test_qq_tool_handle_gateway_event_includes_raw_body_on_empty_payload(tmp_path: Path) -> None:
    tool = QQAutoReplyTool(workspace_dir=tmp_path)

    result = tool.run(
        {
            "command": "handle_gateway_event",
            "event": {},
            "raw_body": '{"post_type":"message"}',
        }
    )

    assert result.success is False
    assert "raw_body={\"post_type\":\"message\"}" in result.output


def test_webhook_handler_reads_chunked_body() -> None:
    handler = _QQWebhookRequestHandler.__new__(_QQWebhookRequestHandler)
    handler.headers = Message()
    handler.headers["Transfer-Encoding"] = "chunked"
    handler.rfile = BytesIO(b'7\r\n{"a":1}\r\n0\r\n\r\n')

    assert handler._read_request_body() == b'{"a":1}'


def test_qq_tool_pause_resume_and_open_log(tmp_path: Path) -> None:
    tool = QQAutoReplyTool(workspace_dir=tmp_path)

    configured = tool.run(
        {
            "command": "configure",
            "enabled": False,
            "private_enabled": False,
            "target_group_id": "g002",
            "private_delay_sec": 90,
            "custom_prompt": "简短、礼貌",
            "cooldown_sec": 45,
            "self_user_id": "myself",
            "gateway_mode": "mock",
        }
    )
    assert configured.success
    assert tool.enabled is False
    assert tool.private_enabled is False
    assert tool.cooldown_sec == 45

    paused = tool.run({"command": "pause"})
    assert paused.success
    assert tool.paused is True

    resumed = tool.run({"command": "resume"})
    assert resumed.success
    assert tool.paused is False

    log_info = tool.run({"command": "open_log"})
    assert log_info.success
    assert str(tool.log_path) in log_info.output


def test_qq_tool_bind_local_client_records_binding(tmp_path: Path) -> None:
    tool = QQAutoReplyTool(workspace_dir=tmp_path)

    result = tool.run(
        {
            "command": "bind_local_client",
            "gateway_mode": "mock",
            "app_title_keyword": "QQ",
            "process_name": "QQ.exe",
            "executable_path": r"C:\\Program Files\\Tencent\\QQ\\QQ.exe",
            "window_title": "腾讯QQ",
            "connect_now": False,
        }
    )

    assert result.success
    assert tool.client_binding is not None
    assert tool.client_binding.app_title_keyword == "QQ"
    assert tool.client_binding.process_name == "QQ.exe"
    assert tool.client_binding.window_title == "腾讯QQ"

    status = tool.run({"command": "get_status"})
    assert status.success
    assert isinstance(status.meta.get("binding"), dict)
    assert status.meta["binding"]["app_title_keyword"] == "QQ"


def test_qq_tool_auto_bind_local_client_discovers_exe(tmp_path: Path) -> None:
    exe_path = tmp_path / "Tencent" / "QQ" / "QQ.exe"
    exe_path.parent.mkdir(parents=True, exist_ok=True)
    exe_path.write_text("fake qq executable", encoding="utf-8")

    tool = QQAutoReplyTool(workspace_dir=tmp_path)
    result = tool.run(
        {
            "command": "bind_local_client_auto",
            "gateway_mode": "mock",
            "search_roots": [str(tmp_path)],
            "connect_now": False,
        }
    )

    assert result.success
    assert tool.client_binding is not None
    assert tool.client_binding.executable_path == str(exe_path)
    assert tool.client_binding.app_title_keyword == "QQ"
    assert "绑定成功" in result.output


def test_qq_tool_auto_bind_local_client_recurses_nested_paths(tmp_path: Path) -> None:
    exe_path = tmp_path / "AppData" / "Local" / "Tencent" / "QQNT" / "Bin" / "QQ.exe"
    exe_path.parent.mkdir(parents=True, exist_ok=True)
    exe_path.write_text("fake qq executable", encoding="utf-8")

    tool = QQAutoReplyTool(workspace_dir=tmp_path)
    result = tool.run(
        {
            "command": "bind_local_client_auto",
            "gateway_mode": "mock",
            "search_roots": [str(tmp_path)],
            "connect_now": False,
        }
    )

    assert result.success
    assert tool.client_binding is not None
    assert tool.client_binding.executable_path == str(exe_path)



def test_qq_tool_auto_bind_local_client_reports_failure_when_missing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(qq_auto_reply_module, "discover_local_qq_client", lambda search_roots=None: None)

    tool = QQAutoReplyTool(workspace_dir=tmp_path)
    result = tool.run(
        {
            "command": "bind_local_client_auto",
            "gateway_mode": "mock",
            "search_roots": [str(tmp_path / "missing")],
            "connect_now": False,
        }
    )

    assert not result.success
    assert "绑定失败" in result.output
    assert isinstance(result.meta.get("binding"), dict)


def test_windows_gateway_connects_or_launches_with_fallback(monkeypatch) -> None:
    class FakeApp:
        def __init__(self, backend: str) -> None:
            self.backend = backend
            self.calls: list[tuple[str, str]] = []

        def connect(self, **kwargs):
            self.calls.append(("connect", repr(kwargs)))
            if "path" in kwargs:
                raise RuntimeError("connect by path failed")
            return self

        def start(self, executable_path: str):
            self.calls.append(("start", executable_path))
            return self

    fake_app_module = types.ModuleType("pywinauto.application")
    setattr(fake_app_module, "Application", FakeApp)
    fake_root_module = types.ModuleType("pywinauto")
    setattr(fake_root_module, "application", fake_app_module)
    monkeypatch.setitem(sys.modules, "pywinauto", fake_root_module)
    monkeypatch.setitem(sys.modules, "pywinauto.application", fake_app_module)

    import clawmini.adapters.qq_adapter as qq_adapter_module

    monkeypatch.setattr(qq_adapter_module.importlib.util, "find_spec", lambda name: object())

    gateway = WindowsQQGateway(app_title_keyword="QQ")
    binding = gateway.bind_local_client(
        app_title_keyword="QQ",
        executable_path=r"C:\\Program Files\\Tencent\\QQ\\QQ.exe",
        window_title="腾讯QQ",
        connect_now=True,
    )

    assert binding.connected is True
    assert "启动并绑定" in binding.notes or "已连接到本地 QQ 客户端" in binding.notes


def test_qq_status_in_windows_mode_has_binding_placeholder(tmp_path: Path) -> None:
    tool = QQAutoReplyTool(workspace_dir=tmp_path)
    tool.gateway_mode = "windows"

    status = tool.run({"command": "get_status"})
    assert status.success
    assert isinstance(status.meta.get("binding"), dict)
    assert status.meta["binding"]["app_title_keyword"] == "QQ"


def test_qq_configure_in_windows_mode_keeps_binding_placeholder(tmp_path: Path) -> None:
    tool = QQAutoReplyTool(workspace_dir=tmp_path)
    tool.gateway_mode = "windows"

    result = tool.run(
        {
            "command": "configure",
            "target_group_id": "g-windows",
            "self_user_id": "self-windows",
        }
    )

    assert result.success
    assert isinstance(result.meta.get("binding"), dict)
    assert result.meta["binding"]["connected"] is False
    assert result.meta["binding"]["notes"]
