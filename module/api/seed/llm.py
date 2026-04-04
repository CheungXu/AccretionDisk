"""字节 Seed 大模型接口。"""

from __future__ import annotations

import base64
import binascii
import json
import mimetypes
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib import error, parse, request


DEFAULT_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3/responses"
DEFAULT_MODEL_NAME = "doubao-seed-2-0-pro-260215"
DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[3] / "config" / "seed.json"
DEFAULT_IMAGE_MIME_TYPE = "image/jpeg"


class SeedAPIError(RuntimeError):
    """Seed 接口请求异常。"""


@dataclass
class SeedLLMClient:
    """字节 Seed 大模型客户端。"""

    api_key: str | None = None
    model_name: str = DEFAULT_MODEL_NAME
    base_url: str = DEFAULT_BASE_URL
    timeout: int = 60
    config_path: str | Path | None = None
    default_image_mime_type: str = DEFAULT_IMAGE_MIME_TYPE
    default_headers: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.api_key is None:
            self.api_key = self._load_api_key()
        if not self.api_key:
            raise SeedAPIError(
                "缺少 API Key，请先设置 ARK_API_KEY，或在 config/seed.json 中配置 api_key。"
            )

    def generate_response(
        self,
        messages: list[dict[str, Any]],
        *,
        model_name: str | None = None,
        **extra_body: Any,
    ) -> dict[str, Any]:
        """基于消息列表生成原始响应。"""

        request_payload = self._build_messages_payload(
            messages=messages,
            model_name=model_name or self.model_name,
            extra_body=extra_body,
        )
        return self._post_json(request_payload)

    def generate_text(
        self,
        messages: list[dict[str, Any]],
        *,
        model_name: str | None = None,
        **extra_body: Any,
    ) -> str:
        """基于消息列表生成文本结果。"""

        response = self.generate_response(
            messages=messages,
            model_name=model_name,
            **extra_body,
        )
        return self.extract_text(response)

    @staticmethod
    def extract_text(response: dict[str, Any]) -> str:
        """从 responses 接口返回中提取文本。"""

        output_text = response.get("output_text")
        if isinstance(output_text, str) and output_text:
            return output_text

        text_segments: list[str] = []
        for output_item in response.get("output", []):
            if not isinstance(output_item, dict):
                continue
            for content_item in output_item.get("content", []):
                if not isinstance(content_item, dict):
                    continue
                if (
                    content_item.get("type") in {"output_text", "text"}
                    and content_item.get("text")
                ):
                    text_segments.append(str(content_item["text"]))

        if text_segments:
            return "\n".join(text_segments)

        raise SeedAPIError("接口返回成功，但未能提取到文本内容。")

    def _build_messages_payload(
        self,
        *,
        messages: list[dict[str, Any]],
        model_name: str,
        extra_body: dict[str, Any],
    ) -> dict[str, Any]:
        normalized_messages = self._normalize_messages(messages)
        request_payload: dict[str, Any] = {
            "model": model_name,
            "input": normalized_messages,
        }
        request_payload.update(extra_body)
        return request_payload

    def _normalize_messages(
        self,
        messages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if not messages:
            raise SeedAPIError("messages 不能为空。")

        normalized_messages: list[dict[str, Any]] = []
        for message in messages:
            if not isinstance(message, dict):
                raise SeedAPIError("messages 中存在非法消息对象。")

            role = message.get("role")
            if role not in {"system", "user", "assistant"}:
                raise SeedAPIError("消息 role 仅支持 system、user、assistant。")

            content = message.get("content")
            normalized_content = self._normalize_message_content(content)
            normalized_messages.append(
                {
                    "role": role,
                    "content": normalized_content,
                }
            )

        return normalized_messages

    def _normalize_message_content(
        self,
        content: Any,
    ) -> list[dict[str, str]]:
        # 支持三种常用写法：
        # 1. 直接传字符串，自动视为 input_text
        # 2. 传列表，列表元素可为字符串或结构化内容块
        # 3. 传单个结构化内容块字典
        if isinstance(content, str):
            return [{"type": "input_text", "text": content}]

        if isinstance(content, dict):
            return [self._normalize_content_item(content)]

        if isinstance(content, list):
            normalized_items: list[dict[str, str]] = []
            for item in content:
                if isinstance(item, str):
                    normalized_items.append({"type": "input_text", "text": item})
                    continue
                if isinstance(item, dict):
                    normalized_items.append(self._normalize_content_item(item))
                    continue
                raise SeedAPIError("消息 content 列表中存在非法内容项。")
            if not normalized_items:
                raise SeedAPIError("消息 content 不能为空列表。")
            return normalized_items

        raise SeedAPIError("消息 content 必须为字符串、字典或列表。")

    def _normalize_content_item(self, content_item: dict[str, Any]) -> dict[str, str]:
        content_type = content_item.get("type")

        if content_type in {None, "input_text", "text"}:
            text = content_item.get("text")
            if not isinstance(text, str) or not text.strip():
                raise SeedAPIError("文本内容块缺少有效 text。")
            return {
                "type": "input_text",
                "text": text,
            }

        if content_type in {"input_image", "image"}:
            image_value = (
                content_item.get("image_url")
                or content_item.get("image_path")
                or content_item.get("image_base64")
            )
            if image_value is None:
                raise SeedAPIError("图片内容块缺少图片数据。")

            if "image_base64" in content_item:
                normalized_image = self._normalize_image_dict(
                    {
                        "image_base64": str(content_item["image_base64"]),
                        "mime_type": str(
                            content_item.get("mime_type") or self.default_image_mime_type
                        ),
                    }
                )
            elif "image_path" in content_item:
                normalized_image = self._normalize_image_dict(
                    {"image_path": str(content_item["image_path"])}
                )
            else:
                normalized_image = self._normalize_image_input(str(content_item["image_url"]))

            return {
                "type": "input_image",
                "image_url": normalized_image,
            }

        raise SeedAPIError(f"不支持的内容类型: {content_type}")

    def _normalize_image_input(self, image_input: str | dict[str, str]) -> str:
        if isinstance(image_input, dict):
            return self._normalize_image_dict(image_input)

        if not isinstance(image_input, str):
            raise SeedAPIError("image_inputs 中存在不支持的图片输入类型。")

        normalized_input = image_input.strip()
        if not normalized_input:
            raise SeedAPIError("image_inputs 中存在空图片输入。")

        if self._is_http_url(normalized_input):
            return normalized_input
        if self._is_data_uri(normalized_input):
            return normalized_input

        local_path = Path(normalized_input).expanduser()
        if local_path.exists() and local_path.is_file():
            return self._encode_local_image_to_data_uri(local_path)

        return self._encode_base64_to_data_uri(normalized_input)

    def _normalize_image_dict(self, image_input: dict[str, str]) -> str:
        # 字典形式便于显式传入 base64 与 mime_type，减少自动猜测。
        image_url = image_input.get("image_url")
        if image_url:
            return self._normalize_image_input(image_url)

        local_path = image_input.get("image_path")
        if local_path:
            return self._encode_local_image_to_data_uri(Path(local_path).expanduser())

        image_base64 = image_input.get("image_base64")
        if image_base64:
            mime_type = image_input.get("mime_type") or self.default_image_mime_type
            return self._encode_base64_to_data_uri(image_base64, mime_type=mime_type)

        raise SeedAPIError(
            "图片字典输入必须包含 image_url、image_path 或 image_base64 之一。"
        )

    def _encode_local_image_to_data_uri(self, image_path: Path) -> str:
        if not image_path.exists() or not image_path.is_file():
            raise SeedAPIError(f"本地图片不存在: {image_path}")

        try:
            image_bytes = image_path.read_bytes()
        except OSError as exc:
            raise SeedAPIError(f"读取本地图片失败: {image_path}") from exc

        mime_type = self._infer_mime_type(image_bytes, image_path.name)
        base64_text = base64.b64encode(image_bytes).decode("utf-8")
        return f"data:{mime_type};base64,{base64_text}"

    def _encode_base64_to_data_uri(
        self,
        image_base64: str,
        *,
        mime_type: str | None = None,
    ) -> str:
        normalized_base64 = image_base64.strip()
        if not normalized_base64:
            raise SeedAPIError("Base64 图片内容不能为空。")

        try:
            image_bytes = base64.b64decode(normalized_base64, validate=True)
        except binascii.Error as exc:
            raise SeedAPIError("Base64 图片内容不合法。") from exc

        resolved_mime_type = mime_type or self._infer_mime_type(image_bytes)
        return f"data:{resolved_mime_type};base64,{normalized_base64}"

    def _infer_mime_type(
        self,
        image_bytes: bytes,
        file_name: str | None = None,
    ) -> str:
        inferred_mime_type = self._infer_mime_type_from_bytes(image_bytes)
        if inferred_mime_type:
            return inferred_mime_type

        if file_name:
            guessed_mime_type, _ = mimetypes.guess_type(file_name)
            if guessed_mime_type and guessed_mime_type.startswith("image/"):
                return guessed_mime_type

        return self.default_image_mime_type

    @staticmethod
    def _infer_mime_type_from_bytes(image_bytes: bytes) -> str | None:
        if image_bytes.startswith(b"\xff\xd8\xff"):
            return "image/jpeg"
        if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
            return "image/png"
        if image_bytes.startswith((b"GIF87a", b"GIF89a")):
            return "image/gif"
        if image_bytes.startswith(b"RIFF") and image_bytes[8:12] == b"WEBP":
            return "image/webp"
        if image_bytes.startswith(b"BM"):
            return "image/bmp"
        return None

    @staticmethod
    def _is_http_url(value: str) -> bool:
        parsed_url = parse.urlparse(value)
        return parsed_url.scheme in {"http", "https"} and bool(parsed_url.netloc)

    @staticmethod
    def _is_data_uri(value: str) -> bool:
        return value.startswith("data:image/") and ";base64," in value

    def _load_api_key(self) -> str | None:
        env_api_key = os.getenv("ARK_API_KEY")
        if env_api_key:
            return env_api_key

        config_path = Path(self.config_path) if self.config_path else DEFAULT_CONFIG_PATH
        if not config_path.exists():
            return None

        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise SeedAPIError(f"读取配置文件失败: {config_path}") from exc
        except json.JSONDecodeError as exc:
            raise SeedAPIError(f"配置文件不是合法 JSON: {config_path}") from exc

        api_key = config.get("api_key")
        if isinstance(api_key, str) and api_key.strip():
            return api_key.strip()
        return None

    def _post_json(self, request_payload: dict[str, Any]) -> dict[str, Any]:
        request_headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        request_headers.update(self.default_headers)

        request_data = json.dumps(request_payload).encode("utf-8")
        http_request = request.Request(
            url=self.base_url,
            data=request_data,
            headers=request_headers,
            method="POST",
        )

        try:
            with request.urlopen(http_request, timeout=self.timeout) as response:
                raw_response_text = response.read().decode("utf-8")
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise SeedAPIError(f"Seed 接口请求失败，HTTP {exc.code}: {detail}") from exc
        except error.URLError as exc:
            raise SeedAPIError(f"Seed 接口网络异常: {exc}") from exc

        try:
            return json.loads(raw_response_text)
        except json.JSONDecodeError as exc:
            raise SeedAPIError(f"Seed 接口返回非 JSON 内容: {raw_response_text}") from exc
