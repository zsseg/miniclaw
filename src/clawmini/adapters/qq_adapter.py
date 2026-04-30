"""QQ 适配层：抽象 QQ 客户端交互能力。"""

from __future__ import annotations

import importlib.util
import os
import re
import subprocess
import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol


def _pywinauto_install_hint() -> str:
    return "请先执行 `python -m pip install pywinauto` 安装依赖后再重试。"


@dataclass(slots=True)
class QQMessage:
    """QQ 消息结构。"""

    source: str  # group / private
    chat_id: str
    sender_id: str
    text: str
    timestamp: datetime = field(default_factory=datetime.now)
    mentioned: bool = False
    mention_all: bool = False
    sender_name: str = ""
    sender_avatar: str = ""
    group_name: str = ""
    group_avatar: str = ""
    image_refs: list[str] = field(default_factory=list)


@dataclass(slots=True)
class QQGatewayEvent:
    """网关侧原始事件结构。"""

    source: str  # group / private
    chat_id: str
    sender_id: str
    text: str
    mentions: list[str] = field(default_factory=list)
    mention_all: bool = False
    timestamp: datetime = field(default_factory=datetime.now)
    sender_name: str = ""
    sender_avatar: str = ""
    group_name: str = ""
    group_avatar: str = ""
    image_refs: list[str] = field(default_factory=list)

    def to_message(self, self_user_id: str) -> QQMessage:
        """转换为智能体内部消息结构，并完成 @我 判定。"""
        mentioned = bool(self_user_id) and (self_user_id in self.mentions)
        # 如果 mentions 列表中没有匹配到，但文本中包含 @QQ 号也算被提及
        if not mentioned and self_user_id and self.text:
            mentioned = f"@{self_user_id}" in self.text
        if self.mention_all:
            mentioned = False
        return QQMessage(
            source=self.source,
            chat_id=self.chat_id,
            sender_id=self.sender_id,
            text=self.text,
            timestamp=self.timestamp,
            mentioned=mentioned,
            mention_all=self.mention_all,
            sender_name=self.sender_name,
            sender_avatar=self.sender_avatar,
            group_name=self.group_name,
            group_avatar=self.group_avatar,
            image_refs=list(self.image_refs),
        )


def build_gateway_event(payload: dict[str, Any]) -> QQGatewayEvent:
    """将网关原始字典转换为标准事件。"""
    def _unwrap_payload(candidate: Any) -> dict[str, Any]:
        if not isinstance(candidate, dict):
            return {}
        current = candidate
        while True:
            next_payload: dict[str, Any] | None = None
            for key in ("payload", "event", "data", "body", "content"):
                nested = current.get(key)
                if not isinstance(nested, dict):
                    continue
                nested_keys = set(nested)
                if nested_keys & {
                    "message_type",
                    "post_type",
                    "detail_type",
                    "type",
                    "chat_type",
                    "group_id",
                    "user_id",
                    "chat_id",
                    "sender_id",
                    "raw_message",
                    "message",
                    "text",
                }:
                    next_payload = {**current, **nested}
                    break
            if next_payload is None:
                return current
            current = next_payload

    payload = _unwrap_payload(payload)

    def _event_kind(value: Any) -> str:
        return str(value or "").strip().lower()

    def _chat_id_from_payload(source: str, data: dict[str, Any]) -> str:
        if source == "group":
            for key in ("group_id", "chat_id", "peer_id", "conversation_id"):
                value = data.get(key)
                if value not in (None, ""):
                    return str(value)
        for key in ("user_id", "chat_id", "peer_id", "conversation_id", "sender_id"):
            value = data.get(key)
            if value not in (None, ""):
                return str(value)
        return ""

    def _sender_id_from_payload(data: dict[str, Any]) -> str:
        sender = data.get("sender") if isinstance(data.get("sender"), dict) else {}
        if isinstance(sender, dict):
            for key in ("user_id", "sender_id", "id"):
                value = sender.get(key)
                if value not in (None, ""):
                    return str(value)
        for key in ("sender_id", "user_id", "from_user_id", "id"):
            value = data.get(key)
            if value not in (None, ""):
                return str(value)
        return "anon"

    def _sender_name_from_payload(data: dict[str, Any]) -> str:
        sender = data.get("sender") if isinstance(data.get("sender"), dict) else {}
        if isinstance(sender, dict):
            for key in ("nickname", "card", "name", "display_name"):
                value = sender.get(key)
                if value not in (None, ""):
                    return str(value)
        for key in ("sender_name", "nickname", "card", "display_name", "name"):
            value = data.get(key)
            if value not in (None, ""):
                return str(value)
        return ""

    def _group_meta_from_payload(data: dict[str, Any]) -> tuple[str, str]:
        group_name = ""
        group_avatar = ""
        for key in ("group_name", "group_title", "chat_name", "conversation_name", "guild_name"):
            value = data.get(key)
            if value not in (None, ""):
                group_name = str(value)
                break
        for key in ("group_avatar", "group_avatar_url", "avatar", "avatar_url", "group_icon"):
            value = data.get(key)
            if value not in (None, ""):
                group_avatar = str(value)
                break
        group = data.get("group") if isinstance(data.get("group"), dict) else {}
        if isinstance(group, dict):
            if not group_name:
                for key in ("name", "title", "group_name"):
                    value = group.get(key)
                    if value not in (None, ""):
                        group_name = str(value)
                        break
            if not group_avatar:
                for key in ("avatar", "avatar_url", "icon"):
                    value = group.get(key)
                    if value not in (None, ""):
                        group_avatar = str(value)
                        break
        return group_name, group_avatar

    def _extract_text_mentions_and_images(message: Any) -> tuple[str, list[str], bool, list[str]]:
        if isinstance(message, str):
            # 从 CQ 码和纯文本 @ 中提取提及
            cq_ids = re.findall(r'\[CQ:at,qq=(\d+)\]', message)
            plain_ids = re.findall(r'(?:^|\s)@(\d+)', message)
            at_ids = list(dict.fromkeys([*cq_ids, *plain_ids]))
            cleaned = re.sub(r'\[CQ:at,qq=(\d+)\]', r'@\1', message)
            # 提取 CQ 码中的图片 URL（NapCat string 格式）
            cq_image_urls = re.findall(r'\[CQ:image[^\]]*?url=([^\],\s]+)', message)
            # 提取闪照/贴图等
            cq_flash_urls = re.findall(r'\[CQ:flash[^\]]*?url=([^\],\s]+)', message)
            cq_sticker_urls = re.findall(r'\[CQ:(?:sticker|mface|face)[^\]]*?url=([^\],\s]+)', message)
            all_cq_images = list(dict.fromkeys(cq_image_urls + cq_flash_urls + cq_sticker_urls))
            # 清理 CQ 码，只保留文本
            cleaned = re.sub(r'\[CQ:image[^\]]*\]', '', cleaned)
            cleaned = re.sub(r'\[CQ:flash[^\]]*\]', '', cleaned)
            cleaned = re.sub(r'\[CQ:face[^\]]*\]', '', cleaned)
            cleaned = re.sub(r'\[CQ:sticker[^\]]*\]', '', cleaned)
            cleaned = re.sub(r'\[CQ:emoji[^\]]*\]', '', cleaned)
            cleaned = re.sub(r'\[CQ:mface[^\]]*\]', '', cleaned)
            cleaned = cleaned.strip()
            return cleaned, at_ids, False, all_cq_images
        if isinstance(message, list):
            parts: list[str] = []
            mentions: list[str] = []
            image_refs: list[str] = []
            mention_all = False
            for segment in message:
                if not isinstance(segment, dict):
                    continue
                seg_type = str(segment.get("type", "")).lower()
                seg_data_raw = segment.get("data")
                seg_data = seg_data_raw if isinstance(seg_data_raw, dict) else {}
                if seg_type == "text":
                    parts.append(str(seg_data.get("text", "")))
                elif seg_type in {"at", "mention"}:
                    qq = str(seg_data.get("qq", seg_data.get("user_id", ""))).strip()
                    if qq:
                        mentions.append(qq)
                        parts.append(f"@{qq}")
                    if qq.lower() == "all":
                        mention_all = True
                elif seg_type in {"image", "pic", "image_file", "sticker", "face", "emoji", "mface", "flash"}:
                    for key in ("url", "image", "image_url", "file_url", "file", "path", "src", "thumb", "preview", "emoji_url"):
                        value = seg_data.get(key)
                        if value not in (None, ""):
                            image_refs.append(str(value).strip())
                            break
                    if seg_type in {"face", "emoji"} and not image_refs:
                        face_id = seg_data.get("id", seg_data.get("face_id", seg_data.get("emoji_id", "")))
                        if face_id not in (None, ""):
                            parts.append(f"[表情:{face_id}]")
                else:
                    plain_text = str(seg_data.get("text", "")).strip()
                    if plain_text:
                        parts.append(plain_text)
            return "".join(parts).strip(), mentions, mention_all, image_refs
        return "", [], False, []

    explicit_source = _event_kind(payload.get("source"))
    message_kind = _event_kind(
        payload.get("message_type")
        or payload.get("post_type")
        or payload.get("detail_type")
        or payload.get("chat_type")
        or payload.get("type")
    )
    if message_kind or any(key in payload for key in ("message_type", "post_type", "detail_type", "chat_type", "type", "group_id", "user_id", "chat_id", "sender_id")):
        if explicit_source in {"group", "private"}:
            source = explicit_source
        else:
            source = "group" if message_kind in {"group", "group_message", "message.group"} or "group" in message_kind else "private"
        chat_id = _chat_id_from_payload(source, payload)
        sender_id = _sender_id_from_payload(payload)
        sender_name = _sender_name_from_payload(payload)
        sender_avatar = str(payload.get("sender_avatar", payload.get("avatar", "")) or "")
        group_name, group_avatar = _group_meta_from_payload(payload)
        text, mentions, mention_all, image_refs = _extract_text_mentions_and_images(payload.get("message", payload.get("raw_message", payload.get("text", ""))))
        if not text:
            text = str(payload.get("raw_message", payload.get("message", "")))
        if not text and isinstance(payload.get("message"), dict):
            text = str(payload["message"].get("text", ""))
        if not text:
            text = str(payload.get("text", ""))
        if not text and image_refs:
            text = "图片消息"
        if not mentions:
            mentions_raw = payload.get("mentions", [])
            if isinstance(mentions_raw, list):
                mentions = [str(item) for item in mentions_raw]
            elif isinstance(mentions_raw, str) and mentions_raw.strip():
                mentions = [m.strip() for m in mentions_raw.split(",") if m.strip()]
        # 如果 mentions 仍为空，尝试从文本中解析 @QQ 格式
        if not mentions and text:
            at_ids = re.findall(r'@(\d+)', text)
            mentions = list(dict.fromkeys(at_ids))  # 去重保序
        return QQGatewayEvent(
            source=source,
            chat_id=chat_id,
            sender_id=sender_id,
            text=text,
            mentions=mentions,
            mention_all=mention_all or bool(payload.get("mention_all", False)),
            sender_name=sender_name,
            sender_avatar=sender_avatar,
            group_name=group_name,
            group_avatar=group_avatar,
            image_refs=image_refs,
        )

    mentions_raw = payload.get("mentions", [])
    mentions: list[str]
    if isinstance(mentions_raw, list):
        mentions = [str(item) for item in mentions_raw]
    elif isinstance(mentions_raw, str) and mentions_raw.strip():
        mentions = [m.strip() for m in mentions_raw.split(",") if m.strip()]
    else:
        mentions = []

    return QQGatewayEvent(
        source=explicit_source or str(payload.get("source", "private")),
        chat_id=_chat_id_from_payload(explicit_source or str(payload.get("source", "private")), payload),
        sender_id=_sender_id_from_payload(payload),
        text=str(payload.get("text", payload.get("raw_message", ""))),
        mentions=mentions,
        mention_all=bool(payload.get("mention_all", False)),
        sender_name=_sender_name_from_payload(payload),
        sender_avatar=str(payload.get("sender_avatar", payload.get("avatar", "")) or ""),
        group_name=_group_meta_from_payload(payload)[0],
        group_avatar=_group_meta_from_payload(payload)[1],
        image_refs=[],
    )


def _send_onebot_http_message(
    api_base_url: str,
    access_token: str,
    chat_id: str,
    text: str,
    message_type: str,
    auto_escape: bool = True,
) -> dict[str, Any]:
    """通过 NapCat/OneBot HTTP 接口发送消息。

    Args:
        api_base_url: NapCat HTTP API 基址。
        access_token: API 访问令牌。
        chat_id: 群号或用户 ID。
        text: 消息文本（可使用 CQ 码如 [CQ:file,...]）。
        message_type: "group" 或 "private"。
        auto_escape: 是否转义 CQ 码。发送文件等含 CQ 码的消息时应设为 False。
    """
    base_url = api_base_url.strip().rstrip("/")
    if not base_url:
        raise ValueError("未配置 NapCat API 基址。")

    plugin_suffix = "/plugin/napcat-plugin-builtin/api"

    def _add_candidate(candidates: list[str], candidate: str) -> None:
        normalized = candidate.strip().rstrip("/")
        if normalized and normalized not in candidates:
            candidates.append(normalized)

    candidates: list[str] = []
    _add_candidate(candidates, base_url)
    if base_url.endswith(plugin_suffix):
        root_base = base_url[: -len(plugin_suffix)].rstrip("/")
        _add_candidate(candidates, root_base)
        _add_candidate(candidates, f"{root_base}/api")
    else:
        _add_candidate(candidates, f"{base_url}{plugin_suffix}")
        _add_candidate(candidates, f"{base_url}/api")
        if base_url.endswith("/api"):
            _add_candidate(candidates, base_url[: -len("/api")].rstrip("/"))

    def _coerce_onebot_id(value: str) -> int | str:
        stripped = str(value).strip()
        if stripped.isdigit():
            try:
                return int(stripped)
            except ValueError:
                return stripped
        return stripped

    payload: dict[str, Any] = {"message": text, "auto_escape": auto_escape}
    payload["user_id" if message_type == "private" else "group_id"] = _coerce_onebot_id(chat_id)
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if access_token.strip():
        token = access_token.strip()
        headers["Authorization"] = f"Bearer {token}"
        headers["X-Access-Token"] = token
    last_error: Exception | None = None
    for candidate_base in candidates:
        if candidate_base.endswith("/send_group_msg") or candidate_base.endswith("/send_private_msg"):
            endpoint = candidate_base
        elif message_type == "private":
            endpoint = f"{candidate_base}/send_private_msg"
        else:
            endpoint = f"{candidate_base}/send_group_msg"

        request = urllib.request.Request(endpoint, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                response_body = response.read().decode("utf-8", errors="ignore")
            if "not found" in response_body.lower():
                last_error = ValueError(f"{endpoint} 返回 Not Found")
                continue
            parsed_response: dict[str, Any] | None = None
            try:
                parsed = json.loads(response_body)
                if isinstance(parsed, dict):
                    parsed_response = parsed
            except Exception:
                parsed_response = None

            if isinstance(parsed_response, dict):
                status = str(parsed_response.get("status", "")).lower()
                retcode = parsed_response.get("retcode")
                if status and status != "ok":
                    last_error = ValueError(f"{endpoint} 返回失败：status={status} retcode={retcode} body={response_body}")
                    continue
                if retcode not in {None, 0, "0"}:
                    last_error = ValueError(f"{endpoint} 返回失败：retcode={retcode} body={response_body}")
                    continue

            return {"endpoint": endpoint, "response": response_body, "parsed_response": parsed_response}
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code == 404:
                continue
            raise
        except urllib.error.URLError as exc:
            last_error = exc
            continue

    if last_error is not None:
        raise last_error
    raise ValueError("未能调用 NapCat OneBot HTTP 接口。")


@dataclass(slots=True)
class QQClientBinding:
    """本地 QQ 客户端绑定信息。"""

    app_title_keyword: str
    process_name: str = ""
    executable_path: str = ""
    window_title: str = ""
    connected: bool = False
    bound_at: datetime = field(default_factory=datetime.now)
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "app_title_keyword": self.app_title_keyword,
            "process_name": self.process_name,
            "executable_path": self.executable_path,
            "window_title": self.window_title,
            "connected": self.connected,
            "bound_at": self.bound_at.isoformat(timespec="seconds"),
            "notes": self.notes,
        }


class QQGateway(Protocol):
    """QQ 网关协议。

    任何真实或模拟实现都应至少提供文本发送能力。
    """

    def send_text(self, chat_id: str, text: str, message_type: str = "group") -> None:
        """发送文本消息。"""

    def send_file(
        self,
        chat_id: str,
        file_path: str,
        message_type: str = "group",
        file_name: str = "",
    ) -> None:
        """发送文件到群聊或私聊。

        Args:
            chat_id: 群号或用户 ID。
            file_path: 本地文件的绝对路径。
            message_type: "group" 或 "private"。
            file_name: 可选的文件显示名称。
        """

    def bind_local_client(
        self,
        app_title_keyword: str = "QQ",
        process_name: str = "",
        executable_path: str = "",
        window_title: str = "",
        connect_now: bool = True,
    ) -> QQClientBinding:
        """绑定本地 QQ 客户端。"""
        ...

    def auto_bind_local_client(
        self,
        connect_now: bool = True,
        search_roots: list[Path] | None = None,
    ) -> QQClientBinding:
        """一键自动绑定本地 QQ 客户端。"""
        ...


def discover_local_qq_client(search_roots: list[Path] | None = None) -> QQClientBinding | None:
    """从常见安装位置发现本地 QQ 客户端。"""
    candidate_roots: list[Path] = []
    if search_roots:
        candidate_roots.extend(search_roots)
    else:
        default_roots = [
            Path(r"C:\Program Files"),
            Path(r"C:\Program Files (x86)"),
            Path(r"C:\Users") / Path.home().name / "AppData" / "Local",
            Path(r"C:\Users") / Path.home().name / "AppData" / "Roaming",
        ]
        env_vars = [
            os.environ.get("PROGRAMFILES"),
            os.environ.get("PROGRAMFILES(X86)"),
            os.environ.get("LOCALAPPDATA"),
            os.environ.get("APPDATA"),
        ]
        for value in env_vars:
            if value:
                candidate_roots.append(Path(value))
        candidate_roots.extend(default_roots)

    deduped_roots: list[Path] = []
    seen_roots: set[Path] = set()
    for root in candidate_roots:
        try:
            resolved_root = root.resolve()
        except Exception:
            resolved_root = root
        if resolved_root in seen_roots:
            continue
        seen_roots.add(resolved_root)
        deduped_roots.append(resolved_root)
    candidate_roots = deduped_roots

    relative_candidates = [
        Path("Tencent/QQ/QQ.exe"),
        Path("Tencent/QQ/Bin/QQ.exe"),
        Path("Tencent/QQNT/QQ.exe"),
        Path("Tencent/QQNT/Bin/QQ.exe"),
        Path("Tencent/QQNT/QQNT.exe"),
        Path("Tencent/QQNT/Bin/QQNT.exe"),
        Path("Tencent/QQ.exe"),
        Path("Tencent/QQNT.exe"),
        Path("Tencent/QQ/Bin/QQNT.exe"),
        Path("Tencent/QQ/QQNT.exe"),
    ]

    process_names = {"QQ.exe", "QQNT.exe", "QQGame.exe"}
    seen: set[Path] = set()

    for root in candidate_roots:
        for rel in relative_candidates:
            exe_path = (root / rel).resolve()
            if exe_path in seen:
                continue
            seen.add(exe_path)
            if exe_path.exists():
                return QQClientBinding(
                    app_title_keyword="QQ",
                    process_name=exe_path.name,
                    executable_path=str(exe_path),
                    window_title="QQ",
                    connected=False,
                    notes="已自动发现本地 QQ 客户端。",
                )

    # 进一步尝试在常见目录中递归发现 QQ 可执行文件，覆盖非默认安装路径。
    recursive_patterns = ["QQ.exe", "QQNT.exe"]
    for root in candidate_roots:
        for pattern in recursive_patterns:
            try:
                for found in root.rglob(pattern):
                    found_path = found.resolve()
                    if found_path in seen:
                        continue
                    seen.add(found_path)
                    if found_path.exists():
                        return QQClientBinding(
                            app_title_keyword="QQ",
                            process_name=found_path.name,
                            executable_path=str(found_path),
                            window_title="QQ",
                            connected=False,
                            notes="已递归发现本地 QQ 客户端。",
                        )
            except Exception:
                continue

    # 如果 QQ 正在运行，尝试通过任务列表做弱发现，便于“一键绑定”至少记录到进程级信息。
    try:
        result = subprocess.run(
            ["tasklist", "/fo", "csv", "/nh"],
            capture_output=True,
            text=True,
            check=False,
            encoding="utf-8",
            errors="ignore",
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                lower_line = line.lower()
                if not any(name.lower() in lower_line for name in process_names):
                    continue
                parts = [item.strip('"') for item in line.split(",")]
                if parts:
                    process_name = parts[0] if parts else "QQ.exe"
                    return QQClientBinding(
                        app_title_keyword="QQ",
                        process_name=process_name,
                        executable_path="",
                        window_title="QQ",
                        connected=False,
                        notes="已发现正在运行的 QQ 进程，但无法直接获取完整可执行路径。",
                    )
    except Exception:
        pass
    return None


def discover_napcat_http_config(search_roots: list[Path] | None = None) -> dict[str, str] | None:
    """从本地 NapCat 安装目录中发现在线发送配置。"""
    def _find_token(value: Any) -> str:
        if isinstance(value, dict):
            for key in ("token", "access_token", "accessToken", "auth_token", "authToken"):
                raw = value.get(key)
                if isinstance(raw, str) and raw.strip():
                    return raw.strip()
            for nested in value.values():
                token = _find_token(nested)
                if token:
                    return token
        elif isinstance(value, list):
            for item in value:
                token = _find_token(item)
                if token:
                    return token
        return ""

    def _find_http_server_token(value: Any) -> str:
        if isinstance(value, dict):
            http_servers = value.get("httpServers")
            if isinstance(http_servers, list):
                for item in http_servers:
                    token = _find_token(item)
                    if token:
                        return token
            network = value.get("network")
            if isinstance(network, dict):
                token = _find_http_server_token(network)
                if token:
                    return token
        elif isinstance(value, list):
            for item in value:
                token = _find_token(item)
                if token:
                    return token
        return ""

    def _find_http_client_token(value: Any) -> str:
        if isinstance(value, dict):
            http_clients = value.get("httpClients")
            if isinstance(http_clients, list):
                for item in http_clients:
                    token = _find_token(item)
                    if token:
                        return token
            for nested in value.values():
                token = _find_http_client_token(nested)
                if token:
                    return token
        elif isinstance(value, list):
            for item in value:
                token = _find_http_client_token(item)
                if token:
                    return token
        return ""

    def _find_http_client_event_url(value: Any) -> str:
        if isinstance(value, dict):
            http_clients = value.get("httpClients")
            if isinstance(http_clients, list):
                for item in http_clients:
                    if not isinstance(item, dict):
                        continue
                    if item.get("enable") is False:
                        continue
                    raw_url = item.get("url")
                    if isinstance(raw_url, str) and raw_url.strip():
                        return raw_url.strip()
            for nested in value.values():
                found = _find_http_client_event_url(nested)
                if found:
                    return found
        elif isinstance(value, list):
            for item in value:
                found = _find_http_client_event_url(item)
                if found:
                    return found
        return ""

    def _find_account_id(value: Any) -> str:
        if isinstance(value, dict):
            for key in ("account_id", "accountId", "qq", "user_id", "userId", "id"):
                raw = value.get(key)
                if isinstance(raw, (int, str)):
                    digits = "".join(ch for ch in str(raw) if ch.isdigit())
                    if digits:
                        return digits
            for nested in value.values():
                account_id = _find_account_id(nested)
                if account_id:
                    return account_id
        elif isinstance(value, list):
            for item in value:
                account_id = _find_account_id(item)
                if account_id:
                    return account_id
        elif isinstance(value, (int, str)):
            digits = "".join(ch for ch in str(value) if ch.isdigit())
            if digits:
                return digits
        return ""

    candidate_roots: list[Path] = []
    if search_roots:
        candidate_roots.extend(search_roots)
    else:
        candidate_roots.extend([Path.cwd(), Path(__file__).resolve().parents[3], Path.home()])

    deduped_roots: list[Path] = []
    seen_roots: set[Path] = set()
    for root in candidate_roots:
        try:
            resolved_root = root.resolve()
        except Exception:
            resolved_root = root
        if resolved_root in seen_roots:
            continue
        seen_roots.add(resolved_root)
        deduped_roots.append(resolved_root)

    for root in deduped_roots:
        napcat_dirs: list[Path] = []
        if root.name == "NapCat.Shell.Windows.OneKey" and root.is_dir():
            napcat_dirs.append(root)
        try:
            napcat_dirs.extend([item for item in root.rglob("NapCat.Shell.Windows.OneKey") if item.is_dir()])
        except Exception:
            pass

        for napcat_dir in napcat_dirs:
            webui: dict[str, Any] = {}
            try:
                webui_files = list(napcat_dir.rglob("config/webui.json"))
            except Exception:
                webui_files = []
            if not webui_files:
                continue

            try:
                webui = json.loads(webui_files[0].read_text(encoding="utf-8"))
                port = int(webui.get("port", 6099))
            except Exception:
                port = 6099

            api_host = "127.0.0.1"
            api_port = port

            webui_token = ""
            try:
                webui_token = _find_token(webui)
            except Exception:
                webui_token = ""

            access_token = ""
            client_token = ""
            event_post_url = ""

            account_id = ""
            napcat_configs: list[Path] = []
            try:
                config_dir = napcat_dir / "config"
                if config_dir.is_dir():
                    napcat_configs.extend([item for item in config_dir.glob("*.json") if item.is_file()])
                napcat_configs.extend([item for item in napcat_dir.rglob("config/*.json") if item.is_file()])
            except Exception:
                napcat_configs = []
            seen_configs: set[Path] = set()
            for config_file in napcat_configs:
                try:
                    resolved_config = config_file.resolve()
                except Exception:
                    resolved_config = config_file
                if resolved_config in seen_configs:
                    continue
                seen_configs.add(resolved_config)
                stem = config_file.stem
                if "_" in stem:
                    candidate = stem.split("_", 1)[1]
                    if candidate.isdigit():
                        account_id = candidate
                if not account_id:
                    digits = "".join(ch for ch in stem if ch.isdigit())
                    if digits:
                        account_id = digits
                if not access_token:
                    try:
                        config_data = json.loads(config_file.read_text(encoding="utf-8"))
                        access_token = _find_http_server_token(config_data)
                    except Exception:
                        pass
                try:
                    config_data = json.loads(config_file.read_text(encoding="utf-8"))
                    network = config_data.get("network") if isinstance(config_data, dict) else None
                    servers = network.get("httpServers") if isinstance(network, dict) else None
                    if isinstance(servers, list):
                        for server in servers:
                            if not isinstance(server, dict):
                                continue
                            if server.get("enable") is False:
                                continue
                            host_raw = str(server.get("host", "127.0.0.1")).strip()
                            port_raw = server.get("port")
                            try:
                                parsed_port = int(str(port_raw))
                            except (TypeError, ValueError):
                                continue
                            if parsed_port <= 0:
                                continue
                            api_port = parsed_port
                            normalized_host = host_raw
                            if normalized_host in {"", "0.0.0.0", "::", "[::]", "*"}:
                                normalized_host = "127.0.0.1"
                            api_host = normalized_host
                            break
                except Exception:
                    pass
                if not client_token:
                    try:
                        config_data = json.loads(config_file.read_text(encoding="utf-8"))
                        client_token = _find_http_client_token(config_data)
                    except Exception:
                        pass
                if not event_post_url:
                    try:
                        config_data = json.loads(config_file.read_text(encoding="utf-8"))
                        event_post_url = _find_http_client_event_url(config_data)
                    except Exception:
                        pass
                if not account_id:
                    try:
                        config_data = json.loads(config_file.read_text(encoding="utf-8"))
                        account_id = _find_account_id(config_data)
                    except Exception:
                        pass
                if account_id and access_token:
                    break

            return {
                "account_id": account_id,
                "port": str(port),
                "api_base_url": f"http://{api_host}:{api_port}/plugin/napcat-plugin-builtin/api",
                "access_token": access_token,
                "client_token": client_token,
                "event_post_url": event_post_url,
                "webui_token": webui_token,
                "webui_url": f"http://127.0.0.1:{port}/webui",
                "napcat_dir": str(napcat_dir),
            }

    return None


class MockQQGateway:
    """QQ 网关的本地模拟实现。

    该实现不依赖真实 QQ 客户端，便于课程作业演示与测试。
    """

    def __init__(self) -> None:
        self.sent_records: list[dict[str, str]] = []
        self.binding_info: QQClientBinding | None = None
        self.last_send_result: dict[str, Any] | None = None

    def send_text(self, chat_id: str, text: str, message_type: str = "group") -> None:
        """发送文本消息（模拟）。"""
        _ = message_type
        self.last_send_result = {"mode": "mock", "chat_id": chat_id, "text": text, "message_type": message_type}
        self.sent_records.append({"chat_id": chat_id, "text": text})

    def send_file(
        self,
        chat_id: str,
        file_path: str,
        message_type: str = "group",
        file_name: str = "",
    ) -> None:
        """发送文件（模拟）。"""
        _ = message_type
        display_name = file_name or Path(file_path).name
        self.last_send_result = {
            "mode": "mock",
            "chat_id": chat_id,
            "file_path": file_path,
            "file_name": display_name,
            "message_type": message_type,
            "success": True,
        }
        self.sent_records.append({"chat_id": chat_id, "file": file_path, "file_name": display_name})

    def bind_local_client(
        self,
        app_title_keyword: str = "QQ",
        process_name: str = "",
        executable_path: str = "",
        window_title: str = "",
        connect_now: bool = False,
    ) -> QQClientBinding:
        """记录本地 QQ 客户端绑定信息（模拟）。"""
        binding = QQClientBinding(
            app_title_keyword=app_title_keyword,
            process_name=process_name,
            executable_path=executable_path,
            window_title=window_title,
            connected=False,
            notes="mock 网关仅记录绑定信息，未连接真实窗口。",
        )
        self.binding_info = binding
        return binding

    def auto_bind_local_client(
        self,
        connect_now: bool = False,
        search_roots: list[Path] | None = None,
    ) -> QQClientBinding:
        discovered = discover_local_qq_client(search_roots)
        if discovered is None:
            binding = QQClientBinding(
                app_title_keyword="QQ",
                connected=False,
                notes="未发现可自动绑定的本地 QQ 客户端。",
            )
            self.binding_info = binding
            return binding
        discovered.notes = (discovered.notes + "（mock 网关仅记录绑定信息）").strip()
        self.binding_info = discovered
        return discovered


class ManagedQQGateway:
    """托管账号网关（无窗口模式）。

    说明：
    - 不依赖本地 QQ 窗口与 UI 自动化。
    - 作为托管账号占位实现，当前会记录发送请求，便于后续接入服务端网关。
    """

    def __init__(self, account_id: str = "", api_base_url: str = "", access_token: str = "") -> None:
        self.account_id = account_id.strip()
        self.api_base_url = api_base_url.strip().rstrip("/")
        self.access_token = access_token.strip()
        self.sent_records: list[dict[str, str]] = []
        self.binding_info: QQClientBinding | None = None
        self.last_send_result: dict[str, Any] | None = None

    def _resolve_endpoint(self, message_type: str) -> tuple[str, str]:
        if not self.api_base_url:
            return "", ""
        normalized = self.api_base_url.rstrip("/")
        if normalized.endswith("/send_group_msg") or normalized.endswith("/send_private_msg"):
            return normalized, ""
        if message_type == "private":
            return f"{normalized}/send_private_msg", "user_id"
        return f"{normalized}/send_group_msg", "group_id"

    def send_text(self, chat_id: str, text: str, message_type: str = "group") -> None:
        if not self.api_base_url:
            self.last_send_result = {
                "mode": "managed",
                "chat_id": chat_id,
                "text": text,
                "message_type": message_type,
                "success": True,
                "reason": "missing_api_base_url",
            }
            self.sent_records.append({"chat_id": chat_id, "text": text})
            return

        endpoint, _ = self._resolve_endpoint(message_type)
        if not endpoint:
            self.last_send_result = {
                "mode": "managed",
                "chat_id": chat_id,
                "text": text,
                "message_type": message_type,
                "success": False,
                "reason": "missing_endpoint",
            }
            self.sent_records.append({"chat_id": chat_id, "text": text})
            return

        result = _send_onebot_http_message(self.api_base_url, self.access_token, chat_id, text, message_type)
        parsed_response = result.get("parsed_response") if isinstance(result, dict) else None
        unauthorized = False
        if isinstance(parsed_response, dict):
            response_message = str(parsed_response.get("message", "")).lower()
            unauthorized = "unauthorized" in response_message
            if parsed_response.get("code") in {-1, "-1"} and not unauthorized:
                unauthorized = "unauthorized" in str(parsed_response).lower()
        if not unauthorized:
            unauthorized = "unauthorized" in str(result.get("response", "")).lower()
        self.last_send_result = {
            "mode": "managed",
            "chat_id": chat_id,
            "text": text,
            "message_type": message_type,
            "success": not unauthorized,
            "reason": "unauthorized" if unauthorized else "ok",
            **result,
        }
        self.sent_records.append({"chat_id": chat_id, "text": text, "response": str(result.get("response", ""))})

    def send_file(
        self,
        chat_id: str,
        file_path: str,
        message_type: str = "group",
        file_name: str = "",
    ) -> None:
        """通过 NapCat OneBot HTTP API 发送文件到群聊/私聊。

        使用 CQ 码 `[CQ:file,file=file:///absolute/path]` 方式发送，
        NapCat 会自动读取本地文件并上传。
        """
        display_name = file_name or Path(file_path).name

        if not self.api_base_url:
            self.last_send_result = {
                "mode": "managed",
                "chat_id": chat_id,
                "file_path": file_path,
                "file_name": display_name,
                "message_type": message_type,
                "success": True,
                "reason": "missing_api_base_url",
            }
            self.sent_records.append({"chat_id": chat_id, "file": file_path, "file_name": display_name})
            return

        # 构造 CQ 码文件消息
        abs_path = str(Path(file_path).resolve())
        # NapCat 支持 file:// 协议和本地绝对路径
        file_url = f"file:///{abs_path.replace('\\', '/')}"
        cq_message = f"[CQ:file,file={file_url},name={display_name}]"

        endpoint, _ = self._resolve_endpoint(message_type)
        if not endpoint:
            self.last_send_result = {
                "mode": "managed",
                "chat_id": chat_id,
                "file_path": file_path,
                "file_name": display_name,
                "message_type": message_type,
                "success": False,
                "reason": "missing_endpoint",
            }
            self.sent_records.append({"chat_id": chat_id, "file": file_path, "file_name": display_name})
            return

        # 复用 _send_onebot_http_message 但传入 CQ 消息，关闭 auto_escape 避免 CQ 码被转义
        result = _send_onebot_http_message(self.api_base_url, self.access_token, chat_id, cq_message, message_type, auto_escape=False)
        parsed_response = result.get("parsed_response") if isinstance(result, dict) else None
        unauthorized = False
        if isinstance(parsed_response, dict):
            response_message = str(parsed_response.get("message", "")).lower()
            unauthorized = "unauthorized" in response_message
        self.last_send_result = {
            "mode": "managed",
            "chat_id": chat_id,
            "file_path": file_path,
            "file_name": display_name,
            "message_type": message_type,
            "success": not unauthorized,
            "reason": "unauthorized" if unauthorized else "ok",
            **result,
        }
        self.sent_records.append({
            "chat_id": chat_id,
            "file": file_path,
            "file_name": display_name,
            "response": str(result.get("response", "")),
        })

    def bind_local_client(
        self,
        app_title_keyword: str = "QQ",
        process_name: str = "",
        executable_path: str = "",
        window_title: str = "",
        connect_now: bool = False,
    ) -> QQClientBinding:
        _ = process_name, executable_path, window_title, connect_now
        display = f"managed:{self.account_id}" if self.account_id else "managed:qq"
        binding = QQClientBinding(
            app_title_keyword=display,
            connected=True,
            notes="托管账号模式已启用，不依赖本地 QQ 窗口。",
        )
        self.binding_info = binding
        return binding

    def auto_bind_local_client(
        self,
        connect_now: bool = False,
        search_roots: list[Path] | None = None,
    ) -> QQClientBinding:
        _ = connect_now, search_roots
        return self.bind_local_client()


class WindowsQQGateway:
    """Windows QQ 自动化网关骨架。

    说明：
    - 当前实现提供接口与依赖检查，便于后续接入 pywinauto/UIAutomation。
    - 为保证课程作业可运行，默认仍建议使用 `MockQQGateway`。
    """

    def __init__(self, app_title_keyword: str = "QQ", api_base_url: str = "", access_token: str = "") -> None:
        self.app_title_keyword = app_title_keyword
        self.api_base_url = api_base_url.strip().rstrip("/")
        self.access_token = access_token.strip()
        self._dependency_ready = self._check_dependency()
        self.binding_info: QQClientBinding | None = None
        self.last_send_result: dict[str, Any] | None = None
        self.process_name = ""
        self.executable_path = ""
        self.window_title = ""
        if not self._dependency_ready:
            raise RuntimeError(f"未安装 pywinauto，无法启用 windows 网关。{_pywinauto_install_hint()}")

    def _check_dependency(self) -> bool:
        return importlib.util.find_spec("pywinauto") is not None

    def _title_candidates(self, app_title_keyword: str, window_title: str) -> list[str]:
        candidates = [window_title, app_title_keyword, self.app_title_keyword, "腾讯QQ", "QQNT", "QQ"]
        return [item for index, item in enumerate(candidates) if item and item not in candidates[:index]]

    def _connect_existing_or_launch(self, executable_path: str, title_candidates: list[str]) -> tuple[Any, bool, str]:
        """优先连接已运行实例，失败时尝试启动，再按标题回连。"""
        from pywinauto.application import Application  # type: ignore[import-not-found]

        last_error = ""
        for backend in ("uia", "win32"):
            try:
                app = Application(backend=backend)
                if executable_path:
                    try:
                        return app.connect(path=executable_path), True, f"已连接到本地 QQ 客户端（{backend} / path）。"
                    except Exception as exc:  # noqa: BLE001
                        last_error = str(exc)
                        try:
                            launched = Application(backend=backend).start(executable_path)
                            return launched, True, f"已启动并绑定本地 QQ 客户端（{backend} / start）。"
                        except Exception as start_exc:  # noqa: BLE001
                            last_error = str(start_exc)

                for title in title_candidates:
                    try:
                        return app.connect(title_re=title), True, f"已连接到本地 QQ 客户端（{backend} / title={title}）。"
                    except Exception as exc:  # noqa: BLE001
                        last_error = str(exc)
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)

        return None, False, last_error or "未能连接到本地 QQ 客户端。"

    def bind_local_client(
        self,
        app_title_keyword: str = "QQ",
        process_name: str = "",
        executable_path: str = "",
        window_title: str = "",
        connect_now: bool = True,
    ) -> QQClientBinding:
        """绑定本地 QQ 客户端窗口，并尝试建立连接。"""
        self.app_title_keyword = app_title_keyword or self.app_title_keyword
        self.process_name = process_name
        self.executable_path = executable_path
        self.window_title = window_title

        connected = False
        notes = "已记录本地 QQ 客户端绑定信息。"
        if connect_now and self._dependency_ready:
            try:
                target_titles = self._title_candidates(app_title_keyword, window_title)
                app, connected, notes = self._connect_existing_or_launch(executable_path, target_titles)
                if connected:
                    self._bound_app = app
            except Exception as exc:  # noqa: BLE001
                notes = f"已记录绑定信息，但未能立即连接：{exc}"

        binding = QQClientBinding(
            app_title_keyword=self.app_title_keyword,
            process_name=self.process_name,
            executable_path=self.executable_path,
            window_title=self.window_title,
            connected=connected,
            notes=notes,
        )
        self.binding_info = binding
        return binding

    def auto_bind_local_client(
        self,
        connect_now: bool = True,
        search_roots: list[Path] | None = None,
    ) -> QQClientBinding:
        discovered = discover_local_qq_client(search_roots)
        if discovered is None:
            binding = QQClientBinding(
                app_title_keyword=self.app_title_keyword,
                connected=False,
                notes=f"未在常见位置发现 QQ 客户端。若要启用 Windows 网关，请先安装 pywinauto：python -m pip install pywinauto。",
            )
            self.binding_info = binding
            return binding

        return self.bind_local_client(
            app_title_keyword=discovered.app_title_keyword,
            process_name=discovered.process_name,
            executable_path=discovered.executable_path,
            window_title=discovered.window_title,
            connect_now=connect_now,
        )

    def send_text(self, chat_id: str, text: str, message_type: str = "group") -> None:
        """发送文本消息（骨架）。

        TODO:
        1. 连接 QQ 主窗口
        2. 切换会话 chat_id
        3. 写入文本并回车发送
        """
        if self.api_base_url:
            result = _send_onebot_http_message(self.api_base_url, self.access_token, chat_id, text, message_type)
            parsed_response = result.get("parsed_response") if isinstance(result, dict) else None
            unauthorized = False
            if isinstance(parsed_response, dict):
                response_message = str(parsed_response.get("message", "")).lower()
                unauthorized = "unauthorized" in response_message
                if parsed_response.get("code") in {-1, "-1"} and not unauthorized:
                    unauthorized = "unauthorized" in str(parsed_response).lower()
            if not unauthorized:
                unauthorized = "unauthorized" in str(result.get("response", "")).lower()
            self.last_send_result = {
                "mode": "windows",
                "chat_id": chat_id,
                "text": text,
                "message_type": message_type,
                "success": not unauthorized,
                "reason": "unauthorized" if unauthorized else "ok",
                **result,
            }
            return
        _ = message_type
        raise NotImplementedError("WindowsQQGateway.send_text 尚未完成真实 UI 自动化步骤。请先自动填充 NapCat API 基址，或切换到 managed 模式。")
