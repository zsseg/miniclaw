"""QQ 自动回复工具。"""

from __future__ import annotations

import json
import base64
import mimetypes
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable
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
            "receive_token": {"type": "string"},
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
            "subject": {"type": "string"},
            "style": {"type": "string"},
            "constraints": {"type": "string"},
            # send_file 参数
            "file_path": {"type": "string", "description": "要发送的文件的绝对路径"},
            "file_name": {"type": "string", "description": "文件在聊天中显示的名称（可选）"},
            "message_type": {"type": "string", "description": "消息类型：group 或 private"},
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
        self.enable_image_recognition = True
        self.last_reply_api_source = ""
        self.last_reply_api_error = ""
        self.last_reply_api_endpoint = ""
        self.managed_account = ""
        self.managed_api_base_url = ""
        self.managed_access_token = ""
        self.receive_token = ""
        self.app_title_keyword = "QQ"
        self.process_name = ""
        self.executable_path = ""
        self.window_title = ""
        self.client_binding: QQClientBinding | None = None
        self.last_auto_reply: dict[str, datetime] = {}
        self.pending_private: dict[str, dict[str, Any]] = {}
        self.recent_messages: dict[str, list[dict[str, Any]]] = {}
        # 按 (chat_id, sender_id) 分别存储历史，避免群聊不同用户消息混淆
        self.per_user_history: dict[str, list[dict[str, Any]]] = {}
        self.recent_context_limit = 4  # 从 8 减少到 4，避免上下文过度记忆
        self.log_path = workspace_dir / "qq_auto_reply.log"
        self.config_path = workspace_dir / "qq_auto_reply_config.json"
        self._load_config()

    def run(self, arguments: dict[str, Any], progress_callback: Callable[[str], None] | None = None) -> ToolResult:
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
        if command == "build_image_prompt":
            return self._build_image_prompt(arguments)
        if command == "send_file":
            return self._send_file(arguments)
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

    def _image_ref_to_content_part(self, ref: str) -> dict[str, Any] | None:
        cleaned = str(ref or "").strip()
        if not cleaned:
            return None
        if cleaned.startswith("data:image/"):
            return {"type": "image_url", "image_url": {"url": cleaned, "detail": "auto"}}
        if self._is_http_image_ref(cleaned):
            # 下载远程图片并缓存到本地
            local_path = self._download_and_cache_image(cleaned)
            if local_path and local_path.exists():
                cleaned = str(local_path)
            else:
                # 下载失败，直接传递原始 URL
                return {"type": "image_url", "image_url": {"url": cleaned, "detail": "auto"}}

        file_path = Path(cleaned)
        if not file_path.exists() or not file_path.is_file():
            return None
        # 限制文件大小：超过 10MB 的不转 base64
        max_bytes = 10 * 1024 * 1024
        try:
            file_size = file_path.stat().st_size
        except Exception:
            file_size = 0
        if file_size > max_bytes:
            return None
        mime_type, _encoding = mimetypes.guess_type(file_path.name)
        if not mime_type:
            mime_type = "image/png"
        try:
            encoded = base64.b64encode(file_path.read_bytes()).decode("ascii")
        except Exception:
            return None
        data_url = f"data:{mime_type};base64,{encoded}"
        return {"type": "image_url", "image_url": {"url": data_url, "detail": "auto"}}

    def _download_and_cache_image(self, url: str) -> Path | None:
        """下载远程图片到本地缓存目录。"""
        cache_dir = self.workspace_dir / ".image_cache"
        if not cache_dir.exists():
            try:
                cache_dir.mkdir(parents=True, exist_ok=True)
            except Exception:
                return None
        import hashlib
        # 从 URL 后缀猜测扩展名
        url_lower = url.lower().rstrip("/")
        for known_ext in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"):
            if known_ext in url_lower:
                ext = known_ext
                break
        else:
            ext = ".jpg"
        name = hashlib.md5(url.encode()).hexdigest() + ext
        local_path = cache_dir / name
        if local_path.exists():
            return local_path
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = resp.read()
            if len(data) > 10 * 1024 * 1024:
                return None
            local_path.write_bytes(data)
            return local_path
        except Exception:
            return None

    def _build_user_content(self, text: str, context_info: dict[str, Any]) -> str | list[dict[str, Any]]:
        image_refs: list[str] = []
        seen_refs: set[str] = set()
        for item in context_info.get("image_refs", []):
            ref = str(item).strip()
            if not ref or ref in seen_refs:
                continue
            seen_refs.add(ref)
            image_refs.append(ref)
        if self.enable_image_recognition and image_refs:
            # 在文本中标注图片类型信息，辅助 VL 模型理解
            image_hints: list[str] = []
            for ref in image_refs:
                img_type = self._classify_image_type(ref)
                image_hints.append(f"[附带的{img_type}]")
            annotated_text = text
            if image_hints:
                annotated_text = text + "\n\n" + "用户同时也发送了以下内容：" + "；".join(image_hints)
            content: list[dict[str, Any]] = [{"type": "text", "text": annotated_text}]
            for ref in image_refs:
                image_part = self._image_ref_to_content_part(ref)
                if image_part is not None:
                    content.append(image_part)
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

    def _send_file_to_gateway(self, chat_id: str, file_path: str, message_type: str = "group", file_name: str = "") -> ToolResult:
        """通过网关发送文件到群聊/私聊。"""
        if self.gateway_mode == "managed":
            self._refresh_managed_gateway_config()
        try:
            self.gateway.send_file(chat_id=chat_id, file_path=file_path, message_type=message_type, file_name=file_name)
            gateway_result = getattr(self.gateway, "last_send_result", None)
            meta: dict[str, Any] = {
                "chat_id": chat_id,
                "message_type": message_type,
                "file_path": file_path,
                "file_name": file_name or Path(file_path).name,
            }
            if isinstance(gateway_result, dict):
                meta.update(gateway_result)
                if not gateway_result.get("success", True) and self._gateway_result_is_unauthorized(gateway_result):
                    refreshed = self._refresh_managed_gateway_config(force=True)
                    if refreshed:
                        self.gateway.send_file(chat_id=chat_id, file_path=file_path, message_type=message_type, file_name=file_name)
                        retry_result = getattr(self.gateway, "last_send_result", None)
                        if isinstance(retry_result, dict):
                            meta.update(retry_result)
                            meta["retried_after_refresh"] = True
                            if retry_result.get("success", True):
                                return ToolResult(True, "ok", meta)
                            if self._gateway_result_is_unauthorized(retry_result):
                                return ToolResult(False, "NapCat 返回 Unauthorized：请检查 managed_access_token 是否与 NapCat 当前 API token 一致。", meta)
                            return ToolResult(False, f"网关发送文件失败：{retry_result.get('reason', retry_result.get('response', '未知错误'))}", meta)
            if isinstance(gateway_result, dict) and not gateway_result.get("success", True):
                reason = str(gateway_result.get("reason", "发送失败"))
                if self._gateway_result_is_unauthorized(gateway_result):
                    return ToolResult(False, "NapCat 返回 Unauthorized：请检查 managed_access_token 是否与 NapCat 当前 API token 一致。", meta)
                return ToolResult(False, f"网关发送文件失败：{reason}", meta)
            return ToolResult(True, "ok", meta)
        except NotImplementedError as exc:
            return ToolResult(False, f"当前网关暂不支持发送文件：{exc}。可切换网关模式为 managed（托管账号）或 mock。")
        except AttributeError as exc:
            return ToolResult(False, f"当前网关({self.gateway_mode})不支持 send_file。请切换为 managed 网关：qq_auto_reply configure gateway_mode=managed")
        except Exception as exc:  # noqa: BLE001
            return ToolResult(False, f"网关发送文件失败：{exc}")

    def _send_file(self, arguments: dict[str, Any]) -> ToolResult:
        """向群聊或私聊发送文件。

        参数：
        - file_path: 要发送的文件的绝对路径（必填）
        - chat_id: 群号或用户 ID（可选，默认为第一个目标群）
        - message_type: "group" 或 "private"（可选，默认 group）
        - file_name: 文件显示名称（可选，默认使用原文件名）
        """
        file_path = str(arguments.get("file_path", "")).strip()
        if not file_path:
            return ToolResult(False, "send_file 需要 file_path 参数（文件的绝对路径）")

        chat_id = str(arguments.get("chat_id", "")).strip() or (self.target_group_ids[0] if self.target_group_ids else "")
        if not chat_id or chat_id == "demo_chat":
            return ToolResult(False, "send_file 需要有效的 chat_id（群号或用户 ID）")

        message_type = str(arguments.get("message_type", "group")).strip() or "group"
        file_name = str(arguments.get("file_name", "")).strip()

        # 验证文件存在
        path = Path(file_path)
        if not path.exists():
            return ToolResult(False, f"文件不存在：{file_path}")
        if not path.is_file():
            return ToolResult(False, f"路径不是文件：{file_path}")

        # 检查文件大小（NapCat 通常限制 < 20MB）
        file_size = path.stat().st_size
        max_bytes = 20 * 1024 * 1024
        if file_size > max_bytes:
            size_mb = file_size / 1024 / 1024
            return ToolResult(False, f"文件过大：{size_mb:.1f}MB（最大 20MB）")

        if not file_name:
            file_name = path.name

        return self._send_file_to_gateway(
            chat_id=chat_id,
            file_path=str(path.resolve()),
            message_type=message_type,
            file_name=file_name,
        )

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
        roots = [self.workspace_dir, *([p.parent for p in self.workspace_dir.parents])]
        discovered = discover_napcat_http_config(roots)
        if not discovered:
            return False
        changed = False
        # token 类字段只要有新值就覆盖；其他字段仅在空时填充
        for key, attr in (("account_id", "managed_account"), ("api_base_url", "managed_api_base_url"), ("access_token", "managed_access_token"), ("client_token", "receive_token")):
            value = str(discovered.get(key, "")).strip()
            current = str(getattr(self, attr, "")).strip()
            if not value:
                continue
            is_token_field = attr in ("managed_access_token", "receive_token")
            is_url_field = attr == "managed_api_base_url"
            if is_token_field:
                if value != current:
                    setattr(self, attr, value)
                    changed = True
            elif is_url_field:
                # 始终用自动发现的 API 基址，确保端口和路径正确
                if value != current:
                    setattr(self, attr, value)
                    changed = True
            else:
                if not current and value:
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
        elif provider.strip().lower() == "qwen":
            if not normalized:
                return "https://dashscope.aliyuncs.com/compatible-mode/v1"
            normalized = normalized.rstrip("/")
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
        self.receive_token = str(arguments.get("receive_token", self.receive_token)).strip()
        if not self.receive_token:
            self.receive_token = str(arguments.get("client_token", self.receive_token)).strip()
        token_changed = "managed_access_token" in arguments or "receive_token" in arguments
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
        # 刷新自动发现的配置，确保 API 基址和 token 始终与 NapCat 配置一致
        self._refresh_managed_gateway_config()
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
                "enable_image_recognition": self.enable_image_recognition,
                "managed_access_token": self.managed_access_token,
                "receive_token": self.receive_token,
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
            if napcat.get("account_id") and not self.managed_account:
                self.managed_account = napcat["account_id"]
                if not self.self_user_id or self.self_user_id in {"self_user", ""}:
                    self.self_user_id = napcat["account_id"]
            # token 字段始终覆盖，其他字段仅在空时填充
            if napcat.get("access_token"):
                self.managed_access_token = napcat["access_token"]
            if napcat.get("client_token"):
                self.receive_token = napcat["client_token"]
            if napcat.get("api_base_url") and not self.managed_api_base_url:
                self.managed_api_base_url = napcat.get("api_base_url", self.managed_api_base_url)

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
                "receive_token": self.receive_token,
                "event_post_url": napcat.get("event_post_url", "") if napcat else "",
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
            if waited_sec <= self.private_delay_sec:
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
            "image_refs": list(image_refs),
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
        # 全局聊天历史（按 chat_id 聚合，用于群聊总体语境）
        history = self.recent_messages.setdefault(chat_id, [])
        # 按用户分开的历史（用于区分群聊不同用户）
        user_key = f"{chat_id}|{sender_id}"
        user_hist = self.per_user_history.setdefault(user_key, [])
        sender_name = context_info.get("sender_name", "") or sender_id
        group_name = context_info.get("group_name", "")
        group_avatar = context_info.get("group_avatar", "")
        image_refs = [str(item).strip() for item in context_info.get("image_refs", []) if str(item).strip()]

        entry_user = {
            "role": "user",
            "speaker": sender_name,
            "sender_id": sender_id,
            "text": inbound_text[:400],
            "source": source,
            "group_name": group_name,
            "group_avatar": group_avatar,
            "image_refs": image_refs,
        }
        entry_asst = {
            "role": "assistant",
            "speaker": self.self_user_id,
            "sender_id": self.self_user_id,
            "text": outbound_text[:400],
            "source": source,
            "group_name": group_name,
            "group_avatar": group_avatar,
            "image_refs": [],
        }

        # 去重：如果最后一条用户消息（来自同一个人，文本相同），则不重复添加
        # 防止同一事件被触发两次导致历史中出现完全相同的消息
        is_dup = False
        if history:
            # 从末尾反向找最近一条 user 消息
            for item in reversed(history):
                if item["role"] == "user":
                    if item.get("sender_id") == sender_id and item["text"] == inbound_text[:400]:
                        is_dup = True
                    break
        if not is_dup:
            history.append(entry_user)
            history.append(entry_asst)
            self.recent_messages[chat_id] = history[-self.recent_context_limit :]

        if not is_dup:
            user_hist.append(entry_user)
            user_hist.append(entry_asst)
            self.per_user_history[user_key] = user_hist[-(self.recent_context_limit) :]

    def _classify_image_type(self, ref: str) -> str:
        """根据图片引用特征猜测图片类型（表情包/截图/普通图片等）。"""
        lowered = ref.lower()
        # 在 _classify_image_type 和 _build_context_block 中统一使用简短标注，实际内容分析交给了 _describe_image_content
        # 减少误判：只在特征非常明确时分类，不明确时统一返回"图片"让 VL 模型自己判断
        meme_keywords = ["face", "sticker", "mface", "emoji", "bq", "magic", "giphy"]
        if any(kw in lowered for kw in meme_keywords):
            return "表情包/贴图"
        if lowered.endswith(".gif"):
            return "GIF动图"
        if "cache" in lowered or "tmp" in lowered:
            return "QQ缓存图片"
        if any(kw in lowered for kw in ("qq", "qun", "p.qlogo", "localhost:")):
            return "QQ图片"
        return "图片"

    def _describe_image_content(self, image_ref: str, user_text: str) -> str | None:
        """使用 VL 模型描述图片的具体内容，特别是表情包中的文字、梗、表情等。
        独立使用 qwen-vl-plus 进行图片分析，不依赖主回复 provider。
        """
        # 使用内置的 qwen API key 进行图片描述
        vl_api_key = "sk-60e843eb0fa347cda5f78a5b8c4de8f7"
        vl_base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
        vl_model = "qwen-vl-plus"
        endpoint = vl_base_url.rstrip("/") + "/chat/completions"

        # 获取图片 base64
        image_part = self._image_ref_to_content_part(image_ref)
        if image_part is None:
            return None

        desc_prompt = (
            "请仔细分析这张图片，给出准确描述。"
            "1. 如果是表情包/梗图/meme——**逐字提取图中所有文字**，描述人物表情/动作，说明这是什么梗/表达什么情绪。字数不限，务必完整。"
            "2. 如果是截图——**完整提取图中所有关键文字信息**。"
            "3. 如果是普通图片——描述画面主体、场景、颜色、氛围。"
            "不要加前缀，直接用中文回答。"
        )
        payload = {
            "model": vl_model,
            "temperature": 0.2,
            "max_tokens": 150,
            "messages": [
                {"role": "user", "content": [
                    {"type": "text", "text": desc_prompt},
                    image_part,
                ]},
            ],
        }
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            endpoint,
            data=data,
            headers={
                "Authorization": f"Bearer {vl_api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            content = str(body["choices"][0]["message"]["content"]).strip()
            return content if len(content) > 5 else None
        except Exception:
            return None

    def _extract_instruction_from_text(self, text: str) -> tuple[str, dict[str, str]]:
        """从消息中提取显式指令（语气、操作要求等），返回（纯净文本，指令字典）。"""
        instructions: dict[str, str] = {}
        cleaned = text
        # 语气指令
        tone_patterns = [
            (r"用(.{1,20})(?:语气|风格|方式|口吻|调调)", "tone"),
            (r"(?:模仿|模拟|扮演|以)(.{1,20})(?:的[语气风格]|语气|风格|身份)", "tone"),
            (r"(?:翻译成|转为|转成)(.{1,20})", "action"),
            (r"(?:用.{1,10})(?:回复|回答|说|骂|夸|怼)", "tone"),
            (r"(?:骂|夸|怼|嘲讽|鼓励|安慰|批评)(?:他|她|我|ta|一下|几句)?", "tone"),
            (r"(?:简短|详细|幽默|严肃|正式|随意|可爱|高冷|温柔|严厉|专业)", "tone"),
        ]
        for pattern, key in tone_patterns:
            m = re.search(pattern, text)
            if m:
                instructions[key] = m.group(0)[:30]
                # 不移除指令词，保留在上下文中给模型参考

        return cleaned, instructions

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

        sender_id = context_info.get("sender_id", "")
        # 优先使用该用户的个人历史，让 AI 分清不同用户
        user_key = f"{chat_id}|{sender_id}" if sender_id else ""
        if user_key and user_key in self.per_user_history:
            user_history = self.per_user_history.get(user_key, [])
            lines.append("与该用户的最近对话：")
            for item in user_history[-(self.recent_context_limit):]:
                speaker = item.get("speaker", "")
                role = "我" if item.get("role") == "assistant" else "对方"
                line_text = item.get('text', '')
                hist_refs = item.get('image_refs', [])
                if hist_refs:
                    line_text += f" [附带{len(hist_refs)}张图片]"
                lines.append(f"- {role} {speaker}: {line_text}")
        else:
            # 没有个人历史时退回到群聊全局历史
            history = self.recent_messages.get(chat_id, [])
            if history:
                lines.append("群聊最近消息：")
                for item in history[-(self.recent_context_limit):]:
                    speaker = item.get("speaker", "")
                    item_sender = item.get("sender_id", "")
                    role = "我" if item.get("role") == "assistant" else f"{speaker}"
                    line_text = item.get('text', '')
                    hist_refs = item.get('image_refs', [])
                    if hist_refs:
                        line_text += f" [附带{len(hist_refs)}张图片]"
                    lines.append(f"- {role}: {line_text}")

        if image_refs:
            lines.append("图片线索：")
            for ref in image_refs[:3]:  # 从 5 张减少到 3 张
                img_type = self._classify_image_type(ref)
                lines.append(f"- [{img_type}] {ref[:80]}")  # 截断长引用路径

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
        if provider not in {"openai", "deepseek", "qwen"} or not api_key:
            self.last_reply_api_error = "未配置可用的回复 API（provider 或 api_key 缺失）"
            return None
        if not api_key.isascii():
            self.last_reply_api_error = "API Key 含有非 ASCII 字符，请只填写真实 key，不要把说明文字一起粘贴进来"
            return None

        has_image_refs = bool(context_info.get("image_refs"))
        if self.reply_api_model.strip():
            model_name = self.reply_api_model.strip()
        elif provider == "deepseek":
            # DeepSeek 不支持图片输入，使用 deepseek-chat（图片会以 URL 文本形式在上下文中提供）
            model_name = "deepseek-chat"
        elif provider == "qwen":
            model_name = "qwen-vl-plus" if has_image_refs else "qwen-plus"
        elif provider == "openai":
            model_name = "gpt-4o" if has_image_refs else "gpt-4o-mini"
        else:
            model_name = "gpt-4o-mini"
        base_url = self.reply_api_base_url.strip()
        if provider == "deepseek" and not base_url:
            base_url = "https://api.deepseek.com"
        if provider == "deepseek" and base_url.rstrip("/").endswith("/v1"):
            base_url = base_url.rstrip("/")[:-3].rstrip("/")
        if provider == "openai" and not base_url:
            base_url = "https://api.openai.com/v1"
        if provider == "qwen" and not base_url:
            base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
        endpoint = base_url.rstrip("/") + "/chat/completions"
        self.last_reply_api_endpoint = endpoint

        # 从消息中提取显式指令
        _, instructions = self._extract_instruction_from_text(text)
        tone = instructions.get("tone", "")
        action = instructions.get("action", "")

        # 判断当前模型是否支持图片输入
        model_lower = model_name.lower()
        supports_vision = any(kw in model_lower for kw in ("vl", "vision", "gpt-4o", "gpt-4.1"))

        context_block = self._build_context_block(text, context_info)

        # 图片描述单独构建，放到 user_content 而非 system_prompt 中，避免跨轮污染
        image_desc_block = ""
        if has_image_refs:
            image_refs = context_info.get("image_refs", [])
            image_descriptions: list[str] = []
            for ref in list(image_refs)[:3]:
                desc = self._describe_image_content(ref, text[:200])
                if desc:
                    image_descriptions.append(desc)
            if image_descriptions:
                image_desc_block = "\n\n图片内容解析：\n" + "\n".join(f"- {d}" for d in image_descriptions)
                stripped = text.strip()
                if not stripped or stripped in ("图片消息", "图片", ""):
                    text = "用户发送了一张" + image_descriptions[0]
            else:
                image_desc_block = "\n\n注意：当前模型无法解析图片内容。"

        system_prompt = (
            "你是 QQ 自动回复助手，正在和一位真实用户聊天。"
            "请基于上下文信息（场景、说话者、最近对话、图片内容等）生成合适的回复。\n\n"
            "### 核心原则\n"
            "- 回复自然简洁，像正常朋友聊天，不要过度热情、夸张或戏精。\n"
            "- 绝对不要输出 Markdown、编号、项目符号、解释性前言（如「好的」「回复：」）或任何非回复本身的文字。\n"
            "- 每段 20~60 字，一句话能说清就不要分多条。需要分多条时用空行分隔。\n"
            "- 不要刻意表现幽默或活跃，除非消息内容本身适合。平和自然的聊天最优先。\n"
            "- 除非被明确要求，否则不必每句都用感叹号、问句或表情符号结尾。\n\n"
            "### 图片处理\n"
            "如果上下文提供了「图片内容解析」，直接基于解析内容回复，就像你真的看到了图一样。\n"
            "1. 表情包/梗图—自然回应图片表达的情绪或梗，简单一句即可，不用刻意搞笑。\n"
            "2. 截图—提取图中信息直接回答或评论，简洁明了。\n"
            "3. 普通图片—描述画面并自然接话，像「这猫好可爱」「拍得挺好看的」。\n"
            "- 绝不说「我看不见图片」，直接基于已有信息正常回复。\n"
            "- 如果图片信息有限，简单回应即可，不要编造细节。\n\n"
            "### 指令执行\n"
            "- 如果消息中有语气指令（用XX语气回、骂他、夸她）或操作指令（翻译、总结、改成英文），直接执行，不加解释。\n\n"
            "### 上下文\n"
            "- 保持话题连贯，不要突然切换。群聊更随意，私聊更自然。\n"
            "- 参考历史中自己说过的话，不要重复。不确定时诚实说不知道。"
        )
        # 用户自定义提示词为最高优先级
        if self.custom_prompt:
            custom = self.custom_prompt.strip()
            system_prompt += f"\n\n### 🔴 最高优先级指令（来自用户设置）\n用户设置了以下自定义要求，请**最优先遵循**：\n{custom}"
        if tone:
            system_prompt += f"\n\n### 语气指令\n用户要求回复语气——「{tone}」，请严格遵循。"
        if action:
            system_prompt += f"\n\n### 操作指令\n用户要求执行操作——「{action}」，请直接执行。"
        system_prompt += f"\n\n### 当前上下文\n{context_block}"
        user_msg = f"收到的消息：{text}\n\n请结合上下文给出回复。"
        if image_desc_block:
            user_msg += image_desc_block
        user_content = self._build_user_content(user_msg, context_info)

        # 根据是否有图片和指令调整 temperature
        temperature = 0.1
        if has_image_refs:
            temperature = 0.2
        if tone:
            temperature = 0.3

        payload = {
            "model": model_name,
            "temperature": temperature,
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

    def _generate_image_prompt_via_api(self, subject: str, style: str, constraints: str) -> str | None:
        provider = self.reply_api_provider.strip().lower()
        api_key = self.reply_api_key.strip()
        if provider not in {"openai", "deepseek", "qwen"} or not api_key:
            self.last_reply_api_error = "未配置可用的图像提示词 API（provider 或 api_key 缺失）"
            return None
        if not api_key.isascii():
            self.last_reply_api_error = "API Key 含有非 ASCII 字符，请只填写真实 key，不要把说明文字一起粘贴进来"
            return None

        model_name = self.reply_api_model.strip() or ("qwen-plus" if provider == "qwen" else "deepseek-chat" if provider == "deepseek" else "gpt-4o-mini")
        base_url = self.reply_api_base_url.strip()
        if provider == "deepseek" and not base_url:
            base_url = "https://api.deepseek.com"
        if provider == "deepseek" and base_url.rstrip("/").endswith("/v1"):
            base_url = base_url.rstrip("/")[:-3].rstrip("/")
        if provider == "openai" and not base_url:
            base_url = "https://api.openai.com/v1"
        if provider == "qwen" and not base_url:
            base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
        endpoint = base_url.rstrip("/") + "/chat/completions"
        self.last_reply_api_endpoint = endpoint

        system_prompt = (
            "你是专业的文生图提示词助手。请把用户的想法整理成一段适合文生图模型直接使用的提示词。"
            "输出必须简洁、具体、可执行，不要解释，不要分点，不要加标题。"
            "优先补全主体、场景、风格、光影、构图、色彩、镜头感与细节。"
        )
        user_prompt = (
            f"主题：{subject.strip() or '未指定'}\n"
            f"风格：{style.strip() or '自然清晰'}\n"
            f"约束：{constraints.strip() or '无'}\n"
            "请直接输出一段适合文生图模型的中文提示词。"
        )
        payload = {
            "model": model_name,
            "temperature": 0.4,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
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

    def _build_image_prompt(self, arguments: dict[str, Any]) -> ToolResult:
        subject = str(arguments.get("subject", "")).strip()
        style = str(arguments.get("style", "")).strip()
        constraints = str(arguments.get("constraints", "")).strip()
        if not subject and not style and not constraints:
            return ToolResult(False, "build_image_prompt 需要至少提供 subject、style 或 constraints 之一。")

        prompt = self._generate_image_prompt_via_api(subject=subject, style=style, constraints=constraints)
        if prompt:
            return ToolResult(True, prompt, {"prompt": prompt, "reply_source": self.reply_api_provider, "reply_api_provider": self.reply_api_provider, "reply_api_model": self.reply_api_model, "reply_api_base_url": self.reply_api_base_url})

        fallback = "；".join([item for item in [subject, style, constraints] if item])
        if not fallback:
            fallback = "清晰自然的画面"
        prompt = f"主体：{fallback}，画面清晰、构图完整、光影自然、细节丰富，适合直接用于文生图模型。"
        return ToolResult(True, prompt, {"prompt": prompt, "reply_source": "local", "reply_api_provider": self.reply_api_provider, "reply_api_model": self.reply_api_model, "reply_api_base_url": self.reply_api_base_url})

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
            "receive_token": self.receive_token,
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
            # 作为 fallback，尝试从 UI 状态文件读取 API 配置
            self._fallback_api_from_ui_state()
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
            # 如果从历史配置加载后 API 字段仍为空，则 fallback 到 UI 状态
            if not self.reply_api_key or self.reply_api_provider in ("", "mock"):
                self._fallback_api_from_ui_state()
            self.managed_account = str(data.get("managed_account", self.managed_account)).strip()
            self.managed_api_base_url = str(data.get("managed_api_base_url", self.managed_api_base_url)).strip() or self.managed_api_base_url
            self.managed_access_token = str(data.get("managed_access_token", self.managed_access_token)).strip()
            self.receive_token = str(data.get("receive_token", self.receive_token)).strip()
            if not self.receive_token:
                self.receive_token = str(data.get("client_token", self.receive_token)).strip()
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

    def _fallback_api_from_ui_state(self) -> None:
        """从 qq_ui_state.json 回读 API 配置作为 fallback。"""
        ui_state_path = self.workspace_dir / "qq_ui_state.json"
        if not ui_state_path.exists():
            return
        try:
            ui_data = json.loads(ui_state_path.read_text(encoding="utf-8"))
            provider = str(ui_data.get("text_api_provider", "")).strip().lower()
            api_key = str(ui_data.get("text_api_key", "")).strip()
            api_model = str(ui_data.get("text_api_model", "")).strip()
            api_base_url = str(ui_data.get("text_api_base_url", "")).strip()
            if api_key and (not self.reply_api_key or self.reply_api_provider in ("", "mock")):
                self.reply_api_provider = provider or "deepseek"
                self.reply_api_key = api_key
                if api_model:
                    self.reply_api_model = api_model
                if api_base_url:
                    self.reply_api_base_url = self._normalize_reply_api_base_url(self.reply_api_provider, api_base_url)
        except Exception:
            pass
