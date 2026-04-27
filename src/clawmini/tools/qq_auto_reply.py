"""QQ 自动回复工具。"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
import re
import webbrowser
import urllib.request

from clawmini.adapters.qq_adapter import (
    ManagedQQGateway,
    MockQQGateway,
    QQClientBinding,
    QQGateway,
    WindowsQQGateway,
    discover_local_qq_client,
    discover_napcat_http_config,
    build_gateway_event,
)
from clawmini.core.security import sanitize_prompt_injection
from clawmini.tools.base import BaseTool
from clawmini.types import ToolResult


NAPCAT_RELEASE_URL = "https://github.com/NapNeko/NapCatQQ/releases/latest"


class QQAutoReplyTool(BaseTool):
    """模拟 QQ 自动回复工具。

    支持：
    - 配置更新
    - 暂停/恢复
    - 处理群聊@与私聊超时回复
    """

    name = "qq_auto_reply"
    description = "处理 QQ 群聊@与私聊自动回复，含频率控制与注入防护"
    parameters_schema = {
        "type": "object",
        "properties": {
            "command": {"type": "string"},
            "enabled": {"type": "boolean"},
            "private_enabled": {"type": "boolean"},
            "target_group_id": {"type": "string"},
            "target_group_ids": {"type": "array", "items": {"type": "string"}},
            "group_id": {"type": "string"},
            "old_group_id": {"type": "string"},
            "new_group_id": {"type": "string"},
            "private_delay_sec": {"type": "integer"},
            "custom_prompt": {"type": "string"},
            "cooldown_sec": {"type": "integer"},
            "self_user_id": {"type": "string"},
            "gateway_mode": {"type": "string"},
            "reply_api_provider": {"type": "string"},
            "reply_api_model": {"type": "string"},
            "reply_api_key": {"type": "string"},
            "reply_api_base_url": {"type": "string"},
            "enable_image_recognition": {"type": "boolean"},
            "managed_account": {"type": "string"},
            "managed_api_base_url": {"type": "string"},
            "managed_access_token": {"type": "string"},
            "app_title_keyword": {"type": "string"},
            "process_name": {"type": "string"},
            "executable_path": {"type": "string"},
            "window_title": {"type": "string"},
            "connect_now": {"type": "boolean"},
            "search_roots": {"type": "array", "items": {"type": "string"}},
            "source": {"type": "string"},
            "chat_id": {"type": "string"},
            "sender_id": {"type": "string"},
            "sender_name": {"type": "string"},
            "sender_avatar": {"type": "string"},
            "group_name": {"type": "string"},
            "group_avatar": {"type": "string"},
            "text": {"type": "string"},
        },
        "required": ["command"],
    }

    def __init__(self, workspace_dir: Path) -> None:
        super().__init__(workspace_dir)
        self.gateway: QQGateway = ManagedQQGateway()
        self.gateway_mode = "managed"
        self.enabled = True
        self.private_enabled = True
        self.paused = False
        self.target_group_id = "demo_chat"
        self.target_group_ids = ["demo_chat"]
        self.private_delay_sec = 0
        self.custom_prompt = ""
        self.cooldown_sec = 0
        self.self_user_id = "self_user"
        self.reply_api_provider = "mock"
        self.reply_api_model = ""
        self.reply_api_key = ""
        self.reply_api_base_url = ""
        self.enable_image_recognition = False
        self.last_reply_api_source = ""
        self.last_reply_api_error = ""
        self.last_reply_api_endpoint = ""
        self.managed_account = ""
        self.managed_api_base_url = ""
        self.managed_access_token = ""
        self.app_title_keyword = "QQ"
        self.process_name = ""
        self.executable_path = ""
        self.window_title = ""
        self.client_binding: QQClientBinding | None = None
        self.last_auto_reply: dict[str, datetime] = {}
        self.pending_private: dict[str, dict[str, Any]] = {}
        self.recent_messages: dict[str, list[dict[str, Any]]] = {}
        self.recent_context_limit = 8
        self.log_path = workspace_dir / "qq_auto_reply.log"
        self.config_path = workspace_dir / "qq_auto_reply_config.json"
        self._load_config()

    def run(self, arguments: dict[str, Any]) -> ToolResult:
        command = arguments.get("command", "")
        if command == "configure":
            return self._configure(arguments)
        if command == "get_status":
            return self._get_status()
        if command == "set_gateway":
            return self._set_gateway(arguments)
        if command == "add_target_group":
            return self._add_target_group(arguments)
        if command == "remove_target_group":
            return self._remove_target_group(arguments)
        if command == "update_target_group":
            return self._update_target_group(arguments)
        if command == "bind_local_client":
            return self._bind_local_client(arguments)
        if command == "bind_local_client_auto":
            return self._bind_local_client_auto(arguments)
        if command == "bootstrap":
            return self._bootstrap(arguments)
        if command == "download_napcat":
            return self._download_napcat()
        if command == "handle_gateway_event":
            return self._handle_gateway_event(arguments)
        if command == "user_replied":
            return self._user_replied(arguments)
        if command == "poll_pending":
            return self._poll_pending()
        if command == "save_config":
            return self._save_config()
        if command == "load_config":
            return self._load_config()
        if command == "pause":
            self.paused = True
            self._save_config()
            return ToolResult(True, "已进入安静模式（pause）。")
        if command == "resume":
            self.paused = False
            self._save_config()
            return ToolResult(True, "已恢复自动回复。")
        if command == "open_log":
            return ToolResult(True, f"日志路径：{self.log_path}", {"log_path": str(self.log_path)})
        if command == "handle_message":
            return self._handle_message(arguments)
        return ToolResult(False, f"不支持的 command: {command}")

    def _extract_image_refs(self, arguments: dict[str, Any]) -> list[str]:
        refs: list[str] = []
        raw_refs = arguments.get("image_refs", [])
        if isinstance(raw_refs, list):
            for item in raw_refs:
                value = str(item).strip()
                if value:
                    refs.append(value)
        elif isinstance(raw_refs, str) and raw_refs.strip():
            refs.extend([part.strip() for part in re.split(r"[,，;；\s]+", raw_refs) if part.strip()])
        single_ref = str(arguments.get("image_ref", "")).strip()
        if single_ref:
            refs.append(single_ref)
        deduped: list[str] = []
        seen: set[str] = set()
        for ref in refs:
            if ref in seen:
                continue
            seen.add(ref)
            deduped.append(ref)
        return deduped

    def _is_http_image_ref(self, ref: str) -> bool:
        lowered = ref.strip().lower()
        return lowered.startswith("http://") or lowered.startswith("https://")

    def _build_user_content(self, text: str, context_info: dict[str, Any]) -> str | list[dict[str, Any]]:
        image_refs = [str(item).strip() for item in context_info.get("image_refs", []) if str(item).strip()]
        if self.enable_image_recognition and image_refs:
            content: list[dict[str, Any]] = [{"type": "text", "text": text}]
            for ref in image_refs:
                if self._is_http_image_ref(ref):
                    content.append({"type": "image_url", "image_url": {"url": ref, "detail": "auto"}})
            if len(content) > 1:
                return content
        return text

    def _send_via_gateway(self, chat_id: str, reply: str, message_type: str = "group") -> ToolResult:
        if self.gateway_mode == "managed":
            self._refresh_managed_gateway_config()
        try:
            self.gateway.send_text(chat_id=chat_id, text=reply, message_type=message_type)
            gateway_result = getattr(self.gateway, "last_send_result", None)
            meta: dict[str, Any] = {"chat_id": chat_id, "message_type": message_type, "reply": reply}
            if isinstance(gateway_result, dict):
                meta.update(gateway_result)
                if not gateway_result.get("success", True) and self._gateway_result_is_unauthorized(gateway_result):
                    refreshed = self._refresh_managed_gateway_config(force=True)
                    if refreshed:
                        self.gateway.send_text(chat_id=chat_id, text=reply, message_type=message_type)
                        retry_result = getattr(self.gateway, "last_send_result", None)
                        if isinstance(retry_result, dict):
                            meta.update(retry_result)
                            meta["retried_after_refresh"] = True
                            if retry_result.get("success", True):
                                return ToolResult(True, "ok", meta)
                            if self._gateway_result_is_unauthorized(retry_result):
                                return ToolResult(False, "NapCat 返回 Unauthorized：请检查 managed_access_token 是否与 NapCat 当前 API token 一致。", meta)
                            return ToolResult(False, f"网关发送失败：{retry_result.get('reason', retry_result.get('response', '未知错误'))}", meta)
            if isinstance(gateway_result, dict) and not gateway_result.get("success", True):
                reason = str(gateway_result.get("reason", "发送失败"))
                if self._gateway_result_is_unauthorized(gateway_result):
                    return ToolResult(False, "NapCat 返回 Unauthorized：请检查 managed_access_token 是否与 NapCat 当前 API token 一致。", meta)
                return ToolResult(False, f"网关发送失败：{reason}", meta)
            return ToolResult(True, "ok", meta)
        except NotImplementedError as exc:
            return ToolResult(False, f"当前网关暂不支持真实发送：{exc}。可切换网关模式为 managed（托管账号）或 mock。")
        except Exception as exc:  # noqa: BLE001
            return ToolResult(False, f"网关发送失败：{exc}")

    def _gateway_result_is_unauthorized(self, gateway_result: dict[str, Any]) -> bool:
        response = str(gateway_result.get("response", "")).lower()
        reason = str(gateway_result.get("reason", "")).lower()
        if "unauthorized" in response or "unauthorized" in reason:
            return True
        parsed = gateway_result.get("parsed_response")
        if isinstance(parsed, dict):
            if "unauthorized" in str(parsed.get("message", "")).lower():
                return True
            if str(parsed.get("code", "")).strip() == "-1" and "unauthorized" in str(parsed).lower():
                return True
        return False

    def _refresh_managed_gateway_config(self, force: bool = False) -> bool:
        roots = [self.workspace_dir, Path.cwd(), Path.home()]
        discovered = discover_napcat_http_config(roots)
        if not discovered:
            return False
        changed = False
        for key, attr in (("account_id", "managed_account"), ("api_base_url", "managed_api_base_url"), ("access_token", "managed_access_token")):
            value = str(discovered.get(key, "")).strip()
            if value and getattr(self, attr) != value:
                setattr(self, attr, value)
                changed = True
        if changed or force:
            self._set_gateway(
                {
                    "mode": "managed",
                    "managed_account": self.managed_account,
                    "managed_api_base_url": self.managed_api_base_url,
                    "managed_access_token": self.managed_access_token,
                    "app_title_keyword": self.app_title_keyword,
                }
            )
            self._save_config()
        return changed

    def _parse_group_ids(self, raw_target_group_id: Any, raw_target_group_ids: Any) -> list[str]:
        groups: list[str] = []
        if isinstance(raw_target_group_ids, list):
            for item in raw_target_group_ids:
                value = str(item).strip()
                if value:
                    groups.append(value)
        if not groups:
            text = str(raw_target_group_id or "").strip()
            if text:
                parts = re.split(r"[,，;；\s]+", text)
                groups = [part.strip() for part in parts if part.strip()]
        if not groups:
            groups = [self.target_group_id] if str(self.target_group_id).strip() else ["demo_chat"]
        # 去重但保持顺序
        deduped: list[str] = []
        seen: set[str] = set()
        for group in groups:
            if group in seen:
                continue
            seen.add(group)
            deduped.append(group)
        return deduped

    def _normalize_reply_api_base_url(self, provider: str, base_url: str) -> str:
        normalized = str(base_url).strip()
        if provider.strip().lower() == "deepseek":
            if not normalized:
                return "https://api.deepseek.com"
            normalized = normalized.rstrip("/")
            if normalized.endswith("/v1"):
                normalized = normalized[: -len("/v1")].rstrip("/")
        return normalized

    def _configure(self, arguments: dict[str, Any]) -> ToolResult:
        self.enabled = bool(arguments.get("enabled", self.enabled))
        self.private_enabled = bool(arguments.get("private_enabled", self.private_enabled))
        group_ids = self._parse_group_ids(arguments.get("target_group_id", self.target_group_id), arguments.get("target_group_ids"))
        self.target_group_ids = group_ids
        self.target_group_id = ",".join(group_ids)
        self.private_delay_sec = int(arguments.get("private_delay_sec", self.private_delay_sec))
        self.custom_prompt = str(arguments.get("custom_prompt", self.custom_prompt))
        self.cooldown_sec = int(arguments.get("cooldown_sec", self.cooldown_sec))
        self.self_user_id = str(arguments.get("self_user_id", self.self_user_id))
        self.reply_api_provider = str(arguments.get("reply_api_provider", self.reply_api_provider)).strip().lower() or self.reply_api_provider
        self.reply_api_model = str(arguments.get("reply_api_model", self.reply_api_model)).strip()
        self.reply_api_key = str(arguments.get("reply_api_key", self.reply_api_key)).strip()
        self.reply_api_base_url = self._normalize_reply_api_base_url(self.reply_api_provider, str(arguments.get("reply_api_base_url", self.reply_api_base_url)))
        self.enable_image_recognition = bool(arguments.get("enable_image_recognition", self.enable_image_recognition))
        self.managed_account = str(arguments.get("managed_account", self.managed_account)).strip()
        self.managed_api_base_url = str(arguments.get("managed_api_base_url", self.managed_api_base_url)).strip() or self.managed_api_base_url
        self.managed_access_token = str(arguments.get("managed_access_token", self.managed_access_token)).strip()
        token_changed = "managed_access_token" in arguments
        if "gateway_mode" in arguments:
            set_result = self._set_gateway(
                {
                    "mode": arguments.get("gateway_mode"),
                    "managed_account": self.managed_account,
                    "managed_api_base_url": self.managed_api_base_url,
                    "managed_access_token": self.managed_access_token,
                    "app_title_keyword": self.app_title_keyword,
                }
            )
            if not set_result.success:
                return set_result
        if any(key in arguments for key in ["app_title_keyword", "process_name", "executable_path", "window_title"]):
            self._apply_binding_fields(arguments)
        save_result = self._save_config()
        if not save_result.success:
            return save_result
        message = "QQ 自动回复配置已更新。"
        if token_changed:
            message += " Token已更新成功。"
        return ToolResult(True, message, save_result.meta)

    def _add_target_group(self, arguments: dict[str, Any]) -> ToolResult:
        group_id = str(arguments.get("group_id", "")).strip()
        if not group_id:
            return ToolResult(False, "add_target_group 需要 group_id")
        if group_id in self.target_group_ids:
            return ToolResult(True, f"群号已存在：{group_id}", {"target_group_ids": list(self.target_group_ids)})
        self.target_group_ids.append(group_id)
        self.target_group_id = ",".join(self.target_group_ids)
        save_result = self._save_config()
        if not save_result.success:
            return save_result
        return ToolResult(True, f"已新增目标群：{group_id}", save_result.meta)

    def _remove_target_group(self, arguments: dict[str, Any]) -> ToolResult:
        group_id = str(arguments.get("group_id", "")).strip()
        if not group_id:
            return ToolResult(False, "remove_target_group 需要 group_id")
        if group_id not in self.target_group_ids:
            return ToolResult(False, f"目标群不存在：{group_id}")
        self.target_group_ids = [item for item in self.target_group_ids if item != group_id]
        if not self.target_group_ids:
            self.target_group_ids = ["demo_chat"]
        self.target_group_id = ",".join(self.target_group_ids)
        save_result = self._save_config()
        if not save_result.success:
            return save_result
        return ToolResult(True, f"已删除目标群：{group_id}", save_result.meta)

    def _update_target_group(self, arguments: dict[str, Any]) -> ToolResult:
        old_group_id = str(arguments.get("old_group_id", "")).strip()
        new_group_id = str(arguments.get("new_group_id", "")).strip()
        if not old_group_id or not new_group_id:
            return ToolResult(False, "update_target_group 需要 old_group_id 和 new_group_id")
        if old_group_id not in self.target_group_ids:
            return ToolResult(False, f"目标群不存在：{old_group_id}")
        if new_group_id in self.target_group_ids and new_group_id != old_group_id:
            return ToolResult(False, f"目标群已存在：{new_group_id}")
        updated: list[str] = []
        for item in self.target_group_ids:
            updated.append(new_group_id if item == old_group_id else item)
        self.target_group_ids = updated
        self.target_group_id = ",".join(self.target_group_ids)
        save_result = self._save_config()
        if not save_result.success:
            return save_result
        return ToolResult(True, f"已更新目标群：{old_group_id} -> {new_group_id}", save_result.meta)

    def _get_status(self) -> ToolResult:
        """获取当前 QQ 自动回复状态。"""
        binding = self.client_binding
        token_display = self.managed_access_token if self.managed_access_token else "未配置"
        if binding is None and self.gateway_mode in {"windows", "managed"}:
            note = "windows 网关已启用，尚未完成本地绑定。"
            if self.gateway_mode == "managed":
                note = "managed 托管账号模式已启用，不依赖本地 QQ 窗口。"
            binding = QQClientBinding(
                app_title_keyword=self.app_title_keyword,
                process_name=self.process_name,
                executable_path=self.executable_path,
                window_title=self.window_title,
                connected=False,
                notes=note,
            )
        return ToolResult(
            True,
            (
                f"enabled={self.enabled}, paused={self.paused}, private_enabled={self.private_enabled}, "
                f"gateway={self.gateway_mode}, target_group={self.target_group_id}, "
                f"pending_private={len(self.pending_private)}, token={token_display}"
            ),
            {
                "enabled": self.enabled,
                "paused": self.paused,
                "private_enabled": self.private_enabled,
                "gateway_mode": self.gateway_mode,
                "target_group_id": self.target_group_id,
                "target_group_ids": list(self.target_group_ids),
                "self_user_id": self.self_user_id,
                "reply_api_provider": self.reply_api_provider,
                "reply_api_model": self.reply_api_model,
                "reply_api_key": self.reply_api_key,
                "reply_api_base_url": self.reply_api_base_url,
                "managed_access_token": self.managed_access_token,
                "pending_private": len(self.pending_private),
                "pending_private_items": self._pending_private_snapshot(),
                "binding": binding.to_dict() if binding else None,
                "client_binding": binding.to_dict() if binding else None,
            }
        )

    def _handle_gateway_event(self, arguments: dict[str, Any]) -> ToolResult:
        """处理网关原始事件并归一化为内部消息。"""
        payload = arguments.get("event")
        if not isinstance(payload, dict):
            return ToolResult(False, "handle_gateway_event 需要 event(dict) 参数")

        raw_body = str(arguments.get("raw_body", ""))

        event = build_gateway_event(payload)
        if not event.chat_id:
            payload_keys = ",".join(sorted(str(key) for key in payload.keys()))
            summary_bits: list[str] = []
            for key in ("post_type", "message_type", "detail_type", "type", "chat_type", "group_id", "user_id", "chat_id", "sender_id", "raw_message", "text"):
                value = payload.get(key)
                if value not in (None, ""):
                    summary_bits.append(f"{key}={value}")
            summary_text = " | ".join(summary_bits) if summary_bits else f"keys={payload_keys}"
            if raw_body:
                summary_text = f"{summary_text} | raw_body={raw_body}"
            return ToolResult(False, f"handle_gateway_event 解析失败：缺少 chat_id / group_id / user_id。收到字段：{summary_text}。请检查 NapCat 上报的事件结构。")
        if not event.text:
            payload_keys = ",".join(sorted(str(key) for key in payload.keys()))
            summary_bits: list[str] = []
            for key in ("post_type", "message_type", "detail_type", "type", "chat_type", "group_id", "user_id", "chat_id", "sender_id", "raw_message", "text"):
                value = payload.get(key)
                if value not in (None, ""):
                    summary_bits.append(f"{key}={value}")
            summary_text = " | ".join(summary_bits) if summary_bits else f"keys={payload_keys}"
            if raw_body:
                summary_text = f"{summary_text} | raw_body={raw_body}"
            return ToolResult(False, f"handle_gateway_event 解析失败：缺少消息文本。收到字段：{summary_text}。请检查 NapCat 上报的事件是否包含 raw_message 或 message。")
        msg = event.to_message(self_user_id=self.self_user_id)
        return self._handle_message(
            {
                "source": msg.source,
                "chat_id": msg.chat_id,
                "sender_id": msg.sender_id,
                "sender_name": msg.sender_name,
                "sender_avatar": msg.sender_avatar,
                "group_name": msg.group_name,
                "group_avatar": msg.group_avatar,
                "text": msg.text,
                "mentioned": msg.mentioned,
                "mention_all": msg.mention_all,
                "image_refs": list(msg.image_refs),
                "manual_replied": bool(payload.get("manual_replied", False)),
                "waited_sec": int(payload.get("waited_sec", self.private_delay_sec + 1)),
            }
        )

    def _user_replied(self, arguments: dict[str, Any]) -> ToolResult:
        """用户手动回复后取消待发送私聊任务。"""
        chat_id = str(arguments.get("chat_id", ""))
        if not chat_id:
            return ToolResult(False, "user_replied 需要 chat_id")
        removed = self.pending_private.pop(chat_id, None)
        if removed is None:
            return ToolResult(True, f"chat_id={chat_id} 无待取消任务")
        return ToolResult(True, f"已取消待回复私聊任务：{chat_id}")

    def _poll_pending(self) -> ToolResult:
        """轮询并执行到期的私聊自动回复任务。"""
        now = datetime.now()
        due_ids = [cid for cid, item in self.pending_private.items() if item["due_at"] <= now]
        sent = 0
        skipped = 0
        for chat_id in due_ids:
            item = self.pending_private.pop(chat_id)
            if self._is_in_cooldown(chat_id):
                skipped += 1
                continue
            safe_sender = f"user_{abs(hash(item['sender_id'])) % 10000}"
            context_info = {
                "source": str(item.get("source", "private")),
                "chat_id": chat_id,
                "sender_id": str(item.get("sender_id", "")),
                "sender_name": str(item.get("sender_name", "")).strip(),
                "sender_avatar": str(item.get("sender_avatar", "")).strip(),
                "group_name": str(item.get("group_name", "")).strip(),
                "group_avatar": str(item.get("group_avatar", "")).strip(),
                "image_refs": list(item.get("image_refs", [])) if isinstance(item.get("image_refs", []), list) else [],
            }
            reply_parts = self._build_reply_parts(str(item["text"]), context_info=context_info)
            if not reply_parts:
                skipped += 1
                continue
            send_result = self._send_via_gateway(chat_id=chat_id, reply=reply_parts[0], message_type="private")
            if not send_result.success:
                skipped += 1
                continue
            sent_parts = [reply_parts[0]]
            for extra_part in reply_parts[1:]:
                extra_result = self._send_via_gateway(chat_id=chat_id, reply=extra_part, message_type="private")
                if not extra_result.success:
                    skipped += 1
                    break
                sent_parts.append(extra_part)
            self.last_auto_reply[chat_id] = datetime.now()
            combined_reply = "\n\n".join(sent_parts)
            self._append_log(chat_id, safe_sender, str(item["text"]), combined_reply)
            self._remember_recent_exchange(chat_id, context_info["source"], str(item.get("sender_id", "")), str(item["text"]), combined_reply, context_info)
            sent += 1
        return ToolResult(True, f"pending轮询完成：发送={sent}, 跳过={skipped}, 剩余={len(self.pending_private)}")

    def _set_gateway(self, arguments: dict[str, Any]) -> ToolResult:
        """切换 QQ 网关实现。"""
        mode = str(arguments.get("mode", "mock")).lower()
        if mode == "mock":
            self.gateway = MockQQGateway()
            self.gateway_mode = mode
            return ToolResult(True, "已切换到 mock 网关。")
        if mode == "windows":
            try:
                self.gateway = WindowsQQGateway(
                    app_title_keyword=str(arguments.get("app_title_keyword", "QQ")),
                    api_base_url=str(arguments.get("managed_api_base_url", self.managed_api_base_url)).strip(),
                    access_token=str(arguments.get("managed_access_token", self.managed_access_token)).strip(),
                )
                self.gateway_mode = mode
                return ToolResult(True, "已切换到 windows 网关。")
            except Exception as exc:  # noqa: BLE001
                self.gateway = MockQQGateway()
                self.gateway_mode = mode
                install_hint = "请先执行 python -m pip install pywinauto 安装依赖后再重试。"
                if self.client_binding is None:
                    self.client_binding = QQClientBinding(
                        app_title_keyword=self.app_title_keyword,
                        process_name=self.process_name,
                        executable_path=self.executable_path,
                        window_title=self.window_title,
                        connected=False,
                        notes=f"windows 网关占位模式：{exc}。{install_hint}",
                    )
                return ToolResult(True, f"已切换到 windows 占位网关：{exc}。{install_hint}", {"binding": self.client_binding.to_dict() if self.client_binding else None})
        if mode == "managed":
            account = str(arguments.get("managed_account", self.managed_account or self.self_user_id)).strip()
            self.managed_account = account
            self.managed_api_base_url = str(arguments.get("managed_api_base_url", self.managed_api_base_url)).strip() or self.managed_api_base_url
            self.managed_access_token = str(arguments.get("managed_access_token", self.managed_access_token)).strip()
            self.gateway = ManagedQQGateway(
                account_id=account,
                api_base_url=self.managed_api_base_url,
                access_token=self.managed_access_token,
            )
            self.gateway_mode = mode
            self.client_binding = self.gateway.bind_local_client()
            return ToolResult(
                True,
                f"已切换到 managed 托管账号模式：{account or '未指定账号'}。",
                {"binding": self.client_binding.to_dict() if self.client_binding else None},
            )
        return ToolResult(False, f"不支持的网关模式：{mode}")

    def _bootstrap(self, arguments: dict[str, Any]) -> ToolResult:
        """一键自动发现 NapCat、填充配置并绑定客户端。"""
        mode = str(arguments.get("gateway_mode", self.gateway_mode)).lower() or self.gateway_mode
        connect_now = bool(arguments.get("connect_now", True))
        raw_roots = arguments.get("search_roots", [])
        search_roots: list[Path] | None = None
        if isinstance(raw_roots, list):
            values = [Path(str(item)) for item in raw_roots if str(item).strip()]
            search_roots = values or None

        napcat = discover_napcat_http_config(search_roots)
        if napcat is not None:
            if napcat.get("account_id"):
                self.managed_account = napcat["account_id"]
                if not self.self_user_id or self.self_user_id in {"self_user", ""}:
                    self.self_user_id = napcat["account_id"]
            self.managed_api_base_url = napcat.get("api_base_url", self.managed_api_base_url)
            if napcat.get("access_token"):
                self.managed_access_token = napcat["access_token"]

        if mode in {"managed", "windows"}:
            set_result = self._set_gateway(
                {
                    "mode": mode,
                    "app_title_keyword": str(arguments.get("app_title_keyword", self.app_title_keyword)),
                    "managed_account": self.managed_account,
                    "managed_api_base_url": self.managed_api_base_url,
                    "managed_access_token": self.managed_access_token,
                }
            )
            if not set_result.success:
                return set_result

        bind_result = self._bind_local_client_auto(
            {
                "gateway_mode": mode,
                "connect_now": connect_now,
                "search_roots": [str(item) for item in search_roots] if search_roots else [],
                "managed_account": self.managed_account,
                "managed_api_base_url": self.managed_api_base_url,
                "managed_access_token": self.managed_access_token,
            }
        )
        if not bind_result.success and napcat is None:
            return bind_result

        save_result = self._save_config()
        if not save_result.success:
            return save_result

        status = self._get_status().meta
        status.update(
            {
                "napcat": napcat,
                "managed_account": self.managed_account,
                "managed_api_base_url": self.managed_api_base_url,
                "managed_access_token": self.managed_access_token,
            }
        )
        message = "已一键启动并自动填充。"
        if napcat is not None:
            message += f" 已发现 NapCat：{napcat.get('napcat_dir', '')}"
            if napcat.get("client_token") and not napcat.get("access_token"):
                message += " 已发现 httpClients token，但它只用于 NapCat 推送事件，不是发送消息的 HTTP 鉴权 token。"
            if napcat.get("webui_token") and not napcat.get("access_token"):
                message += " 仅发现 WebUI token，请在 onebot11_xxx.json 的 network.httpServers[].token 中配置 HTTP 鉴权 token。"
        if self.managed_access_token:
            message += " Token已同步。"
        return ToolResult(True, message, status)

    def _download_napcat(self) -> ToolResult:
        """打开 NapCat 最新发布页，供用户下载 Windows 一键包。"""
        opened = webbrowser.open_new_tab(NAPCAT_RELEASE_URL)
        if not opened:
            return ToolResult(False, "未能打开浏览器，请手动访问 NapCat 发布页。", {"url": NAPCAT_RELEASE_URL})
        return ToolResult(True, "已打开 NapCat 下载页，请下载 Windows 一键包后运行安装。", {"url": NAPCAT_RELEASE_URL})

    def _reply_api_binding(self) -> dict[str, Any]:
        return {
            "reply_api_provider": self.reply_api_provider,
            "reply_api_model": self.reply_api_model,
            "reply_api_key": self.reply_api_key,
            "reply_api_base_url": self.reply_api_base_url,
            "enable_image_recognition": self.enable_image_recognition,
            "managed_account": self.managed_account,
            "managed_api_base_url": self.managed_api_base_url,
            "managed_access_token": self.managed_access_token,
        }

    def _bind_local_client(self, arguments: dict[str, Any]) -> ToolResult:
        """绑定本地 QQ 客户端。"""
        mode = str(arguments.get("gateway_mode", self.gateway_mode)).lower()
        if mode:
            self._set_gateway(
                {
                    "mode": mode,
                    "app_title_keyword": str(arguments.get("app_title_keyword", self.app_title_keyword)),
                    "managed_account": str(arguments.get("managed_account", self.managed_account)).strip(),
                    "managed_api_base_url": str(arguments.get("managed_api_base_url", self.managed_api_base_url)).strip(),
                    "managed_access_token": str(arguments.get("managed_access_token", self.managed_access_token)).strip(),
                }
            )

        self._apply_binding_fields(arguments)

        connect_now = bool(arguments.get("connect_now", True))
        binding = None
        if hasattr(self.gateway, "bind_local_client"):
            binding = self.gateway.bind_local_client(
                app_title_keyword=self.app_title_keyword,
                process_name=self.process_name,
                executable_path=self.executable_path,
                window_title=self.window_title,
                connect_now=connect_now,
            )
            if isinstance(binding, QQClientBinding):
                self.client_binding = binding
            else:
                self.client_binding = QQClientBinding(
                    app_title_keyword=self.app_title_keyword,
                    process_name=self.process_name,
                    executable_path=self.executable_path,
                    window_title=self.window_title,
                    connected=False,
                    notes="已绑定本地 QQ 客户端，但网关未返回详细状态。",
                )
        else:
            self.client_binding = QQClientBinding(
                app_title_keyword=self.app_title_keyword,
                process_name=self.process_name,
                executable_path=self.executable_path,
                window_title=self.window_title,
                connected=False,
                notes="当前网关不支持本地绑定。",
            )

        self._save_config()
        return ToolResult(
            True,
            f"已绑定本地QQ客户端：{self.app_title_keyword}"
            + (f"，窗口={self.window_title}" if self.window_title else "")
            + ("，已连接" if self.client_binding and self.client_binding.connected else "，已记录绑定信息"),
            {"binding": self.client_binding.to_dict() if self.client_binding else None},
        )

    def _bind_local_client_auto(self, arguments: dict[str, Any]) -> ToolResult:
        """一键自动绑定本地 QQ 客户端。"""
        mode = str(arguments.get("gateway_mode", self.gateway_mode)).lower()
        if mode:
            self._set_gateway(
                {
                    "mode": mode,
                    "app_title_keyword": str(arguments.get("app_title_keyword", self.app_title_keyword)),
                    "managed_account": str(arguments.get("managed_account", self.managed_account)).strip(),
                    "managed_api_base_url": str(arguments.get("managed_api_base_url", self.managed_api_base_url)).strip(),
                    "managed_access_token": str(arguments.get("managed_access_token", self.managed_access_token)).strip(),
                }
            )

        connect_now = bool(arguments.get("connect_now", True))
        raw_roots = arguments.get("search_roots", [])
        search_roots: list[Path] = []
        if isinstance(raw_roots, list):
            for item in raw_roots:
                if str(item).strip():
                    search_roots.append(Path(str(item)))

        discovered = discover_local_qq_client(search_roots if search_roots else None)
        if discovered is None:
            self.client_binding = QQClientBinding(
                app_title_keyword=self.app_title_keyword,
                connected=False,
                notes="未自动发现本地 QQ 客户端，请手动使用浏览选择可执行文件。",
            )
            self._save_config()
            return ToolResult(False, "绑定失败：未自动发现本地 QQ 客户端，请改用手动浏览。", {"binding": self.client_binding.to_dict()})

        self._apply_binding_fields(
            {
                "app_title_keyword": discovered.app_title_keyword,
                "process_name": discovered.process_name,
                "executable_path": discovered.executable_path,
                "window_title": discovered.window_title,
            }
        )

        if hasattr(self.gateway, "bind_local_client"):
            binding = self.gateway.bind_local_client(
                app_title_keyword=self.app_title_keyword,
                process_name=self.process_name,
                executable_path=self.executable_path,
                window_title=self.window_title,
                connect_now=connect_now,
            )
            self.client_binding = binding if isinstance(binding, QQClientBinding) else discovered
            if not self.client_binding.notes:
                self.client_binding.notes = discovered.notes

        self._save_config()
        return ToolResult(
            True,
            f"绑定成功：{self.executable_path or self.app_title_keyword}" + ("，已连接" if self.client_binding and self.client_binding.connected else "，未立即连接"),
            {"binding": self.client_binding.to_dict() if self.client_binding else discovered.to_dict()},
        )

    def _apply_binding_fields(self, arguments: dict[str, Any]) -> None:
        self.app_title_keyword = str(arguments.get("app_title_keyword", self.app_title_keyword))
        self.process_name = str(arguments.get("process_name", self.process_name))
        self.executable_path = str(arguments.get("executable_path", self.executable_path))
        self.window_title = str(arguments.get("window_title", self.window_title))

    def _handle_message(self, arguments: dict[str, Any]) -> ToolResult:
        if not self.enabled or self.paused:
            return ToolResult(True, "自动回复已禁用或处于安静模式。")

        source = str(arguments.get("source", "private"))
        chat_id = str(arguments.get("chat_id", ""))
        sender_id = str(arguments.get("sender_id", "anon"))
        raw_text = str(arguments.get("text", ""))
        text = sanitize_prompt_injection(raw_text)
        image_refs = self._extract_image_refs(arguments)

        if source == "group":
            mentioned = bool(arguments.get("mentioned", False))
            mention_all = bool(arguments.get("mention_all", False))
            if chat_id not in self.target_group_ids:
                return ToolResult(True, "非目标群，已忽略。")
            if mention_all:
                return ToolResult(True, "检测到群@所有人，按规则不触发自动回复。")
            if not mentioned:
                return ToolResult(True, "群消息未明确@我，已忽略。")
        elif source == "private":
            if not self.private_enabled:
                return ToolResult(True, "私聊自动回复未启用。")
            manual_replied = bool(arguments.get("manual_replied", False))
            waited_sec = int(arguments.get("waited_sec", self.private_delay_sec + 1))
            if manual_replied:
                self.pending_private.pop(chat_id, None)
                return ToolResult(True, f"私聊任务已取消：{chat_id}")
            if waited_sec < self.private_delay_sec:
                due_at = datetime.now() + timedelta(seconds=max(self.private_delay_sec - waited_sec, 1))
                self.pending_private[chat_id] = {
                    "sender_id": sender_id,
                    "text": text,
                    "due_at": due_at,
                    "source": source,
                    "sender_name": str(arguments.get("sender_name", "")).strip(),
                    "sender_avatar": str(arguments.get("sender_avatar", "")).strip(),
                    "group_name": str(arguments.get("group_name", "")).strip(),
                    "group_avatar": str(arguments.get("group_avatar", "")).strip(),
                    "image_refs": list(image_refs),
                }
                remain = max(self.private_delay_sec - waited_sec, 1)
                return ToolResult(True, f"私聊已进入等待队列：{chat_id}，约 {remain} 秒后触发。")
        else:
            return ToolResult(False, f"未知消息来源: {source}")

        if self._is_in_cooldown(chat_id):
            return ToolResult(True, "触发频率控制：30秒内不重复回复。")

        safe_sender = f"user_{abs(hash(sender_id)) % 10000}"
        context_info = {
            "source": source,
            "chat_id": chat_id,
            "sender_id": sender_id,
            "sender_name": str(arguments.get("sender_name", "")).strip(),
            "sender_avatar": str(arguments.get("sender_avatar", "")).strip(),
            "group_name": str(arguments.get("group_name", "")).strip(),
            "group_avatar": str(arguments.get("group_avatar", "")).strip(),
            "image_refs": image_refs,
        }
        reply_parts = self._build_reply_parts(text, context_info=context_info)
        if not reply_parts:
            return ToolResult(False, "未生成可发送的回复内容。")

        send_result = self._send_via_gateway(chat_id=chat_id, reply=reply_parts[0], message_type=source)
        if not send_result.success:
            return send_result

        sent_parts = [reply_parts[0]]
        for extra_part in reply_parts[1:]:
            extra_result = self._send_via_gateway(chat_id=chat_id, reply=extra_part, message_type=source)
            if not extra_result.success:
                return extra_result
            sent_parts.append(extra_part)

        self.last_auto_reply[chat_id] = datetime.now()
        combined_reply = "\n\n".join(sent_parts)
        self._append_log(chat_id, safe_sender, text, combined_reply)
        self._remember_recent_exchange(chat_id, source, sender_id, text, combined_reply, context_info)

        meta = dict(send_result.meta) if isinstance(send_result.meta, dict) else {}
        meta.update(
            {
                "chat_id": chat_id,
                "message_type": source,
                "reply": combined_reply,
                "reply_parts": sent_parts,
                "reply_count": len(sent_parts),
                "reply_source": self.last_reply_api_source,
                "reply_api_error": self.last_reply_api_error,
                "reply_api_endpoint": self.last_reply_api_endpoint,
                "reply_api_provider": self.reply_api_provider,
                "reply_api_model": self.reply_api_model,
                "reply_api_base_url": self.reply_api_base_url,
            }
        )
        reply_summary = combined_reply if len(sent_parts) == 1 else f"{len(sent_parts)} 条消息"
        return ToolResult(True, f"已自动回复到 {chat_id}: {reply_summary}", meta)

    def _is_in_cooldown(self, chat_id: str) -> bool:
        last = self.last_auto_reply.get(chat_id)
        if not last:
            return False
        return datetime.now() - last < timedelta(seconds=self.cooldown_sec)

    def _remember_recent_exchange(
        self,
        chat_id: str,
        source: str,
        sender_id: str,
        inbound_text: str,
        outbound_text: str,
        context_info: dict[str, Any],
    ) -> None:
        history = self.recent_messages.setdefault(chat_id, [])
        sender_name = context_info.get("sender_name", "") or sender_id
        group_name = context_info.get("group_name", "")
        group_avatar = context_info.get("group_avatar", "")
        image_refs = [str(item).strip() for item in context_info.get("image_refs", []) if str(item).strip()]

        history.append(
            {
                "role": "user",
                "speaker": sender_name,
                "text": inbound_text[:400],
                "source": source,
                "group_name": group_name,
                "group_avatar": group_avatar,
                "image_refs": image_refs,
            }
        )
        history.append(
            {
                "role": "assistant",
                "speaker": self.self_user_id,
                "text": outbound_text[:400],
                "source": source,
                "group_name": group_name,
                "group_avatar": group_avatar,
                "image_refs": [],
            }
        )
        self.recent_messages[chat_id] = history[-self.recent_context_limit :]

    def _build_context_block(self, text: str, context_info: dict[str, Any]) -> str:
        lines: list[str] = []
        source = context_info.get("source", "private")
        chat_id = context_info.get("chat_id", "")
        sender_name = context_info.get("sender_name", "")
        sender_id = context_info.get("sender_id", "")
        sender_avatar = context_info.get("sender_avatar", "")
        group_name = context_info.get("group_name", "")
        group_avatar = context_info.get("group_avatar", "")
        image_refs = [str(item).strip() for item in context_info.get("image_refs", []) if str(item).strip()]

        if source == "group":
            lines.append(f"群聊场景：群名={group_name or '未提供'} | 群头像={group_avatar or '未提供'} | 群号={chat_id or '未提供'}")
        else:
            lines.append(f"私聊场景：会话={chat_id or '未提供'}")

        if sender_name or sender_id or sender_avatar:
            lines.append(
                f"发言者：{sender_name or '未知昵称'} | ID={sender_id or '未知'} | 头像={sender_avatar or '未提供'}"
            )

        history = self.recent_messages.get(chat_id, [])
        if history:
            lines.append("最近对话：")
            for item in history[-6:]:
                speaker = item.get("speaker", "")
                role = "我" if item.get("role") == "assistant" else "对方"
                lines.append(f"- {role} {speaker}: {item.get('text', '')}")

        if image_refs:
            lines.append("图片线索：")
            for ref in image_refs[:3]:
                lines.append(f"- {ref}")

        lines.append(f"当前消息：{text}")
        return "\n".join(lines)

    def _build_reply_parts(self, text: str, context_info: dict[str, Any] | None = None) -> list[str]:
        context_info = context_info or {}
        self.last_reply_api_source = "local"
        self.last_reply_api_error = ""
        self.last_reply_api_endpoint = ""
        api_reply = self._generate_reply_via_api(text, context_info=context_info)
        if api_reply:
            return self._split_reply_segments(api_reply)

        prompt_tag = f"[{self.custom_prompt}] " if self.custom_prompt else ""
        clean_text = re.sub(r"\s+", " ", text).strip()
        reply = f"{prompt_tag}收到：{clean_text[:120]}。建议你先确认需求细节，我可以继续协助。"
        return self._split_reply_segments(reply)

    def _split_reply_segments(self, reply: str) -> list[str]:
        normalized = re.sub(r"\r\n?", "\n", str(reply)).strip()
        if not normalized:
            return []

        paragraphs = [part.strip() for part in re.split(r"\n\s*\n+", normalized) if part.strip()]
        if len(paragraphs) > 1:
            return [part[:200] for part in paragraphs]

        lines = [line.strip() for line in normalized.split("\n") if line.strip()]
        if len(lines) > 1 and all(re.match(r"^(?:\d+[.)]|[-*•])\s+", line) for line in lines):
            return [line[:200] for line in lines]

        return [normalized[:200]]

    def _generate_reply_via_api(self, text: str, context_info: dict[str, Any] | None = None) -> str | None:
        context_info = context_info or {}
        provider = self.reply_api_provider.strip().lower()
        api_key = self.reply_api_key.strip()
        if provider not in {"openai", "deepseek"} or not api_key:
            self.last_reply_api_error = "未配置可用的回复 API（provider 或 api_key 缺失）"
            return None
        if not api_key.isascii():
            self.last_reply_api_error = "API Key 含有非 ASCII 字符，请只填写真实 key，不要把说明文字一起粘贴进来"
            return None

        model_name = self.reply_api_model.strip() or ("deepseek-chat" if provider == "deepseek" else "gpt-4o-mini")
        base_url = self.reply_api_base_url.strip()
        if provider == "deepseek" and not base_url:
            base_url = "https://api.deepseek.com"
        if provider == "deepseek" and base_url.rstrip("/").endswith("/v1"):
            base_url = base_url.rstrip("/")[:-3].rstrip("/")
        if provider == "openai" and not base_url:
            base_url = "https://api.openai.com/v1"
        endpoint = base_url.rstrip("/") + "/chat/completions"
        self.last_reply_api_endpoint = endpoint

        context_block = self._build_context_block(text, context_info)
        system_prompt = (
            "你是 QQ 自动回复助手。请根据输入生成适合直接发送到 QQ 的中文回复。"
            "如果只需要一条回复，就输出一段简洁、自然、礼貌的内容。"
            "如果需要多条回复，请用空行分成多个自然段，每个自然段表达一个独立意思，"
            "不要输出编号、项目符号前缀、解释、前言或 Markdown。"
            "每段都应尽量短，适合单独作为一条 QQ 消息发送。"
            "不要说自己看不见群头像、图片或图标，也不要解释自己无法观察到这些内容。"
            "如果头像信息不足，不要编造具体图案，只围绕群名、群聊内容和已提供的元信息作答。"
        )
        if self.custom_prompt:
            system_prompt += f" 用户额外要求：{self.custom_prompt}"
        system_prompt += f"\n\n上下文信息：\n{context_block}\n\n请优先参考最近对话、群名、群头像、发言者信息和图片线索来回答。"

        user_content = self._build_user_content(f"收到的消息：{text}\n\n请结合上下文给出回复。", context_info)

        payload = {
            "model": model_name,
            "temperature": 0.3,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
        }
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            endpoint,
            data=data,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            content = str(body["choices"][0]["message"]["content"]).strip()
            self.last_reply_api_source = provider
            self.last_reply_api_error = ""
            return content
        except Exception as exc:
            self.last_reply_api_error = str(exc)
            return None

    def _append_log(self, chat_id: str, sender_id: str, text: str, reply: str) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "time": datetime.now().isoformat(timespec="seconds"),
            "chat_id": chat_id,
            "sender": sender_id,
            "message_summary": text[:60],
            "reply": reply,
        }
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _pending_private_snapshot(self) -> list[dict[str, Any]]:
        """返回待回复私聊队列的可读快照。"""
        now = datetime.now()
        snapshot: list[dict[str, Any]] = []
        for chat_id, item in self.pending_private.items():
            due_at = item.get("due_at")
            seconds_left = None
            due_at_text = ""
            if isinstance(due_at, datetime):
                seconds_left = max(int((due_at - now).total_seconds()), 0)
                due_at_text = due_at.isoformat(timespec="seconds")
            snapshot.append(
                {
                    "chat_id": chat_id,
                    "sender_id": str(item.get("sender_id", "")),
                    "due_at": due_at_text,
                    "seconds_left": seconds_left,
                }
            )
        snapshot.sort(key=lambda item: (item["seconds_left"] is None, item["seconds_left"] or 0, item["chat_id"]))
        return snapshot

    def _save_config(self) -> ToolResult:
        """保存当前 QQ 自动回复配置。"""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        binding = self.client_binding
        if binding is None and self.gateway_mode in {"windows", "managed"}:
            note = "windows 网关已启用，尚未完成本地绑定。"
            if self.gateway_mode == "managed":
                note = "managed 托管账号模式已启用，不依赖本地 QQ 窗口。"
            binding = QQClientBinding(
                app_title_keyword=self.app_title_keyword,
                process_name=self.process_name,
                executable_path=self.executable_path,
                window_title=self.window_title,
                connected=False,
                notes=note,
            )
        data = {
            "enabled": self.enabled,
            "private_enabled": self.private_enabled,
            "paused": self.paused,
            "target_group_id": self.target_group_id,
            "target_group_ids": list(self.target_group_ids),
            "private_delay_sec": self.private_delay_sec,
            "custom_prompt": self.custom_prompt,
            "cooldown_sec": self.cooldown_sec,
            "self_user_id": self.self_user_id,
            "reply_api_provider": self.reply_api_provider,
            "reply_api_model": self.reply_api_model,
            "reply_api_key": self.reply_api_key,
            "reply_api_base_url": self.reply_api_base_url,
            "managed_account": self.managed_account,
            "managed_api_base_url": self.managed_api_base_url,
            "managed_access_token": self.managed_access_token,
            "gateway_mode": self.gateway_mode,
            "app_title_keyword": self.app_title_keyword,
            "process_name": self.process_name,
            "executable_path": self.executable_path,
            "window_title": self.window_title,
            "client_binding": binding.to_dict() if binding else None,
        }
        try:
            self.config_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            meta = dict(data)
            meta["binding"] = binding.to_dict() if binding else None
            return ToolResult(True, f"配置已保存：{self.config_path}", meta)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(False, f"保存配置失败：{exc}")

    def _load_config(self) -> ToolResult:
        """加载 QQ 自动回复配置（若存在）。"""
        if not self.config_path.exists():
            return ToolResult(True, "未发现历史配置，已使用默认配置。")
        try:
            data = json.loads(self.config_path.read_text(encoding="utf-8"))
            self.enabled = bool(data.get("enabled", self.enabled))
            self.private_enabled = bool(data.get("private_enabled", self.private_enabled))
            self.paused = bool(data.get("paused", self.paused))
            self.target_group_id = str(data.get("target_group_id", self.target_group_id))
            self.target_group_ids = self._parse_group_ids(self.target_group_id, data.get("target_group_ids"))
            self.target_group_id = ",".join(self.target_group_ids)
            self.private_delay_sec = int(data.get("private_delay_sec", self.private_delay_sec))
            self.custom_prompt = str(data.get("custom_prompt", self.custom_prompt))
            self.cooldown_sec = int(data.get("cooldown_sec", self.cooldown_sec))
            self.self_user_id = str(data.get("self_user_id", self.self_user_id))
            self.reply_api_provider = str(data.get("reply_api_provider", self.reply_api_provider)).strip().lower() or self.reply_api_provider
            self.reply_api_model = str(data.get("reply_api_model", self.reply_api_model)).strip()
            self.reply_api_key = str(data.get("reply_api_key", self.reply_api_key)).strip()
            self.reply_api_base_url = self._normalize_reply_api_base_url(self.reply_api_provider, str(data.get("reply_api_base_url", self.reply_api_base_url)))
            self.enable_image_recognition = bool(data.get("enable_image_recognition", self.enable_image_recognition))
            self.managed_account = str(data.get("managed_account", self.managed_account)).strip()
            self.managed_api_base_url = str(data.get("managed_api_base_url", self.managed_api_base_url)).strip() or self.managed_api_base_url
            self.managed_access_token = str(data.get("managed_access_token", self.managed_access_token)).strip()
            self.app_title_keyword = str(data.get("app_title_keyword", self.app_title_keyword))
            self.process_name = str(data.get("process_name", self.process_name))
            self.executable_path = str(data.get("executable_path", self.executable_path))
            self.window_title = str(data.get("window_title", self.window_title))
            mode = str(data.get("gateway_mode", self.gateway_mode))
            self._set_gateway({"mode": mode, "managed_account": self.managed_account, "managed_api_base_url": self.managed_api_base_url, "managed_access_token": self.managed_access_token})
            binding = data.get("client_binding")
            if isinstance(binding, dict):
                self.client_binding = QQClientBinding(
                    app_title_keyword=str(binding.get("app_title_keyword", self.app_title_keyword)),
                    process_name=str(binding.get("process_name", self.process_name)),
                    executable_path=str(binding.get("executable_path", self.executable_path)),
                    window_title=str(binding.get("window_title", self.window_title)),
                    connected=bool(binding.get("connected", False)),
                    notes=str(binding.get("notes", "")),
                )
            elif self.gateway_mode in {"windows", "managed"}:
                note = "windows 网关已启用，尚未完成本地绑定。"
                if self.gateway_mode == "managed":
                    note = "managed 托管账号模式已启用，不依赖本地 QQ 窗口。"
                self.client_binding = QQClientBinding(
                    app_title_keyword=self.app_title_keyword,
                    process_name=self.process_name,
                    executable_path=self.executable_path,
                    window_title=self.window_title,
                    connected=False,
                    notes=note,
                )
            return ToolResult(True, f"已加载配置：{self.config_path}", data)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(False, f"加载配置失败：{exc}")
