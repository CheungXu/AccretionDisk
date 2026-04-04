"""字节 Seed 生图接口。"""

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


DEFAULT_IMAGE_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3/images/generations"
DEFAULT_IMAGE_MODEL_NAME = "doubao-seedream-5-0-260128"
DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[3] / "config" / "seed.json"
DEFAULT_IMAGE_MIME_TYPE = "image/jpeg"


class SeedImageAPIError(RuntimeError):
    """Seed 生图接口请求异常。"""


@dataclass
class SeedImageClient:
    """字节 Seed 生图客户端。"""

    api_key: str | None = None
    model_name: str = DEFAULT_IMAGE_MODEL_NAME
    base_url: str = DEFAULT_IMAGE_BASE_URL
    timeout: int = 300
    config_path: str | Path | None = None
    default_image_mime_type: str = DEFAULT_IMAGE_MIME_TYPE
    default_headers: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.api_key is None:
            self.api_key = self._load_api_key()
        if not self.api_key:
            raise SeedImageAPIError(
                "缺少 API Key，请先设置 ARK_API_KEY，或在 config/seed.json 中配置 api_key。"
            )

    def generate(
        self,
        prompt: str,
        *,
        reference_images: list[str | dict[str, str]] | None = None,
        image_count: int = 1,
        model_name: str | None = None,
        response_format: str = "url",
        size: str = "2K",
        stream: bool | None = None,
        watermark: bool = True,
        sequential_image_generation: str | None = None,
        **extra_body: Any,
    ) -> dict[str, Any] | list[dict[str, Any]]:
        """统一生图入口，支持文生图与图生图。"""

        request_payload = self._build_request_payload(
            prompt=prompt,
            reference_images=reference_images,
            image_count=image_count,
            model_name=model_name or self.model_name,
            response_format=response_format,
            size=size,
            stream=stream,
            watermark=watermark,
            sequential_image_generation=sequential_image_generation,
            extra_body=extra_body,
        )
        return self._post_json(request_payload)

    def generate_image_urls(
        self,
        prompt: str,
        *,
        reference_images: list[str | dict[str, str]] | None = None,
        image_count: int = 1,
        model_name: str | None = None,
        response_format: str = "url",
        size: str = "2K",
        stream: bool | None = None,
        watermark: bool = True,
        sequential_image_generation: str | None = None,
        **extra_body: Any,
    ) -> list[str]:
        """生成图片并提取图片 URL 列表。"""

        response = self.generate(
            prompt=prompt,
            reference_images=reference_images,
            image_count=image_count,
            model_name=model_name,
            response_format=response_format,
            size=size,
            stream=stream,
            watermark=watermark,
            sequential_image_generation=sequential_image_generation,
            **extra_body,
        )
        return self.extract_image_urls(response)

    def generate_single_image_url(
        self,
        prompt: str,
        *,
        reference_images: list[str | dict[str, str]] | None = None,
        model_name: str | None = None,
        response_format: str = "url",
        size: str = "2K",
        watermark: bool = True,
        **extra_body: Any,
    ) -> str:
        """生成单张图片并返回唯一 URL。"""

        image_urls = self.generate_image_urls(
            prompt=prompt,
            reference_images=reference_images,
            image_count=1,
            model_name=model_name,
            response_format=response_format,
            size=size,
            stream=False,
            watermark=watermark,
            sequential_image_generation="disabled",
            **extra_body,
        )
        if len(image_urls) != 1:
            raise SeedImageAPIError(f"预期返回 1 张图片，实际得到 {len(image_urls)} 张。")
        return image_urls[0]

    @staticmethod
    def extract_image_urls(response: dict[str, Any] | list[dict[str, Any]]) -> list[str]:
        """从普通响应或流式响应中提取图片 URL。"""

        image_urls: list[str] = []
        seen_urls: set[str] = set()

        def walk(node: Any) -> None:
            if isinstance(node, dict):
                for key, value in node.items():
                    if key in {"url", "image_url"} and isinstance(value, str) and value.strip():
                        if value not in seen_urls:
                            seen_urls.add(value)
                            image_urls.append(value)
                    else:
                        walk(value)
                return

            if isinstance(node, list):
                for item in node:
                    walk(item)

        walk(response)
        if image_urls:
            return image_urls

        raise SeedImageAPIError("接口返回成功，但未能提取到图片 URL。")

    def _build_request_payload(
        self,
        *,
        prompt: str,
        reference_images: list[str | dict[str, str]] | None,
        image_count: int,
        model_name: str,
        response_format: str,
        size: str,
        stream: bool | None,
        watermark: bool,
        sequential_image_generation: str | None,
        extra_body: dict[str, Any],
    ) -> dict[str, Any]:
        if not prompt.strip():
            raise SeedImageAPIError("prompt 不能为空。")
        if image_count <= 0:
            raise SeedImageAPIError("image_count 必须大于 0。")

        resolved_sequential_mode = (
            sequential_image_generation
            if sequential_image_generation is not None
            else ("disabled" if image_count == 1 else "auto")
        )
        if resolved_sequential_mode not in {"disabled", "auto"}:
            raise SeedImageAPIError(
                "sequential_image_generation 仅支持 disabled 或 auto。"
            )

        resolved_stream = stream if stream is not None else image_count > 1

        request_payload: dict[str, Any] = {
            "model": model_name,
            "prompt": prompt,
            "sequential_image_generation": resolved_sequential_mode,
            "response_format": response_format,
            "size": size,
            "stream": resolved_stream,
            "watermark": watermark,
        }

        if image_count > 1:
            request_payload["sequential_image_generation_options"] = {
                "max_images": image_count
            }

        normalized_reference_images = self._normalize_reference_images(
            reference_images or []
        )
        if normalized_reference_images:
            request_payload["image"] = (
                normalized_reference_images[0]
                if len(normalized_reference_images) == 1
                else normalized_reference_images
            )

        request_payload.update(extra_body)
        return request_payload

    def _normalize_reference_images(
        self,
        reference_images: list[str | dict[str, str]],
    ) -> list[str]:
        normalized_images: list[str] = []
        for image_input in reference_images:
            normalized_images.append(self._normalize_image_input(image_input))
        return normalized_images

    def _normalize_image_input(self, image_input: str | dict[str, str]) -> str:
        if isinstance(image_input, dict):
            return self._normalize_image_dict(image_input)

        if not isinstance(image_input, str):
            raise SeedImageAPIError("reference_images 中存在不支持的图片输入类型。")

        normalized_input = image_input.strip()
        if not normalized_input:
            raise SeedImageAPIError("reference_images 中存在空图片输入。")

        if self._is_http_url(normalized_input):
            return normalized_input
        if self._is_data_uri(normalized_input):
            return normalized_input

        local_path = Path(normalized_input).expanduser()
        if local_path.exists() and local_path.is_file():
            return self._encode_local_image_to_data_uri(local_path)

        return self._encode_base64_to_data_uri(normalized_input)

    def _normalize_image_dict(self, image_input: dict[str, str]) -> str:
        # 字典形式更适合显式传入本地路径、URL 或 Base64 内容。
        image_url = image_input.get("image_url")
        if image_url:
            return self._normalize_image_input(image_url)

        image_path = image_input.get("image_path")
        if image_path:
            return self._encode_local_image_to_data_uri(Path(image_path).expanduser())

        image_base64 = image_input.get("image_base64")
        if image_base64:
            mime_type = image_input.get("mime_type") or self.default_image_mime_type
            return self._encode_base64_to_data_uri(image_base64, mime_type=mime_type)

        raise SeedImageAPIError(
            "图片字典输入必须包含 image_url、image_path 或 image_base64 之一。"
        )

    def _encode_local_image_to_data_uri(self, image_path: Path) -> str:
        if not image_path.exists() or not image_path.is_file():
            raise SeedImageAPIError(f"本地图片不存在: {image_path}")

        try:
            image_bytes = image_path.read_bytes()
        except OSError as exc:
            raise SeedImageAPIError(f"读取本地图片失败: {image_path}") from exc

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
            raise SeedImageAPIError("Base64 图片内容不能为空。")

        try:
            image_bytes = base64.b64decode(normalized_base64, validate=True)
        except binascii.Error as exc:
            raise SeedImageAPIError("Base64 图片内容不合法。") from exc

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
            raise SeedImageAPIError(f"读取配置文件失败: {config_path}") from exc
        except json.JSONDecodeError as exc:
            raise SeedImageAPIError(f"配置文件不是合法 JSON: {config_path}") from exc

        api_key = config.get("api_key")
        if isinstance(api_key, str) and api_key.strip():
            return api_key.strip()
        return None

    def _post_json(self, request_payload: dict[str, Any]) -> dict[str, Any] | list[dict[str, Any]]:
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
                content_type = response.headers.get("Content-Type", "")
                raw_response_text = response.read().decode("utf-8")
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise SeedImageAPIError(f"Seed 生图接口请求失败，HTTP {exc.code}: {detail}") from exc
        except error.URLError as exc:
            raise SeedImageAPIError(f"Seed 生图接口网络异常: {exc}") from exc

        if "text/event-stream" in content_type or raw_response_text.lstrip().startswith("data:"):
            return self._parse_sse_response(raw_response_text)

        try:
            return json.loads(raw_response_text)
        except json.JSONDecodeError as exc:
            raise SeedImageAPIError(
                f"Seed 生图接口返回非 JSON 内容: {raw_response_text}"
            ) from exc

    def _parse_sse_response(self, raw_response_text: str) -> list[dict[str, Any]]:
        """解析流式响应，保留事件名和事件数据。"""

        events: list[dict[str, Any]] = []
        for raw_block in raw_response_text.split("\n\n"):
            block = raw_block.strip()
            if not block:
                continue

            event_name: str | None = None
            data_parts: list[str] = []
            for line in block.splitlines():
                stripped_line = line.strip()
                if stripped_line.startswith("event:"):
                    event_name = stripped_line.split(":", 1)[1].strip()
                elif stripped_line.startswith("data:"):
                    data_parts.append(stripped_line.split(":", 1)[1].strip())

            if not data_parts:
                continue

            data_text = "\n".join(data_parts)
            if data_text == "[DONE]":
                event_record: dict[str, Any] = {"data": data_text}
                if event_name:
                    event_record["event"] = event_name
                events.append(event_record)
                continue

            try:
                event_data: Any = json.loads(data_text)
            except json.JSONDecodeError:
                event_data = data_text

            event_record = {"data": event_data}
            if event_name:
                event_record["event"] = event_name
            events.append(event_record)

        if events:
            return events

        raise SeedImageAPIError("流式响应为空，未解析到有效事件。")
