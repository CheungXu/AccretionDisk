"""字节 Seed 生图接口。"""

from __future__ import annotations

import base64
import binascii
import json
import mimetypes
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib import error, parse, request

from .config import load_api_key, load_seed_section


DEFAULT_IMAGE_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3/images/generations"
DEFAULT_IMAGE_MODEL_NAME = "doubao-seedream-5-0-260128"
DEFAULT_IMAGE_MIME_TYPE = "image/jpeg"
DEFAULT_DOWNLOAD_PREFIX = "seed_image"


class SeedImageAPIError(RuntimeError):
    """Seed 生图接口请求异常。"""


@dataclass
class SeedImageClient:
    """字节 Seed 生图客户端。"""

    api_key: str | None = None
    model_name: str | None = None
    base_url: str = DEFAULT_IMAGE_BASE_URL
    timeout: int | None = None
    config_path: str | Path | None = None
    params_config_path: str | Path | None = None
    default_image_mime_type: str = DEFAULT_IMAGE_MIME_TYPE
    default_download_prefix: str = DEFAULT_DOWNLOAD_PREFIX
    response_format: str | None = None
    size: str | None = None
    stream: bool | None = None
    watermark: bool | None = None
    sequential_image_generation: str | None = None
    strict_image_count: bool | None = None
    retry_on_partial: bool | None = None
    max_partial_retries: int | None = None
    default_headers: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self._apply_config_defaults()
        if self.api_key is None:
            self.api_key = load_api_key(self.config_path)
        if not self.api_key:
            raise SeedImageAPIError(
                "缺少 API Key，请先设置 ARK_API_KEY，或在 config/seed_key.json 中配置 api_key。"
            )

    def generate(
        self,
        prompt: str,
        *,
        reference_images: list[str | dict[str, str]] | None = None,
        image_count: int = 1,
        model_name: str | None = None,
        response_format: str | None = None,
        size: str | None = None,
        stream: bool | None = None,
        watermark: bool | None = None,
        sequential_image_generation: str | None = None,
        **extra_body: Any,
    ) -> dict[str, Any] | list[dict[str, Any]]:
        """统一生图入口，支持文生图与图生图。"""

        resolved_response_format = response_format or self.response_format or "url"
        resolved_size = size or self.size or "2K"
        resolved_stream = self.stream if stream is None else stream
        resolved_watermark = self.watermark if watermark is None else watermark
        resolved_sequential_image_generation = (
            self.sequential_image_generation
            if sequential_image_generation is None
            else sequential_image_generation
        )

        request_payload = self._build_request_payload(
            prompt=prompt,
            reference_images=reference_images,
            image_count=image_count,
            model_name=model_name or self.model_name,
            response_format=resolved_response_format,
            size=resolved_size,
            stream=resolved_stream,
            watermark=bool(resolved_watermark),
            sequential_image_generation=resolved_sequential_image_generation,
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
        response_format: str | None = None,
        size: str | None = None,
        stream: bool | None = None,
        watermark: bool | None = None,
        sequential_image_generation: str | None = None,
        strict_image_count: bool | None = None,
        retry_on_partial: bool | None = None,
        max_partial_retries: int | None = None,
        **extra_body: Any,
    ) -> list[str]:
        """生成图片并提取图片 URL 列表。组图不足时可按差值自动重试。"""

        if strict_image_count is None:
            strict_image_count = self.strict_image_count
        if retry_on_partial is None:
            retry_on_partial = self.retry_on_partial
        if max_partial_retries is None:
            max_partial_retries = self.max_partial_retries

        if max_partial_retries < 0:
            raise SeedImageAPIError("max_partial_retries 不能小于 0。")

        collected_image_urls: list[str] = []
        seen_urls: set[str] = set()
        remaining_image_count = image_count
        attempt_count = 0

        while remaining_image_count > 0:
            attempt_count += 1
            response = self.generate(
                prompt=prompt,
                reference_images=reference_images,
                image_count=remaining_image_count,
                model_name=model_name,
                response_format=response_format,
                size=size,
                stream=stream,
                watermark=watermark,
                sequential_image_generation=sequential_image_generation,
                **extra_body,
            )
            batch_image_urls = self.extract_image_urls(response)
            for image_url in batch_image_urls:
                if image_url not in seen_urls:
                    seen_urls.add(image_url)
                    collected_image_urls.append(image_url)

            remaining_image_count = max(image_count - len(collected_image_urls), 0)
            if remaining_image_count == 0:
                return collected_image_urls

            actual_batch_count = self._extract_generated_image_count(response) or len(
                batch_image_urls
            )
            used_retry_count = attempt_count - 1
            can_retry = (
                retry_on_partial
                and image_count > 1
                and actual_batch_count > 0
                and used_retry_count < max_partial_retries
            )
            if can_retry:
                continue

            self._validate_generated_image_count(
                expected_image_count=image_count,
                actual_image_count=len(collected_image_urls),
                strict_image_count=strict_image_count,
            )
            return collected_image_urls

        return collected_image_urls

    def generate_single_image_url(
        self,
        prompt: str,
        *,
        reference_images: list[str | dict[str, str]] | None = None,
        model_name: str | None = None,
        response_format: str | None = None,
        size: str | None = None,
        watermark: bool | None = None,
        strict_image_count: bool | None = None,
        retry_on_partial: bool | None = None,
        max_partial_retries: int | None = None,
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
            strict_image_count=strict_image_count,
            retry_on_partial=retry_on_partial,
            max_partial_retries=max_partial_retries,
            **extra_body,
        )
        if len(image_urls) != 1:
            raise SeedImageAPIError(f"预期返回 1 张图片，实际得到 {len(image_urls)} 张。")
        return image_urls[0]

    def save_images(
        self,
        image_urls: list[str],
        output_dir: str | Path,
        *,
        file_name_prefix: str | None = None,
        file_names: list[str] | None = None,
    ) -> list[Path]:
        """将图片 URL 下载到本地目录。"""

        if not image_urls:
            raise SeedImageAPIError("image_urls 不能为空。")

        save_dir = Path(output_dir).expanduser()
        save_dir.mkdir(parents=True, exist_ok=True)

        if file_names is not None and len(file_names) != len(image_urls):
            raise SeedImageAPIError("file_names 数量必须与 image_urls 数量一致。")

        resolved_prefix = file_name_prefix or self.default_download_prefix
        saved_paths: list[Path] = []
        for index, image_url in enumerate(image_urls, start=1):
            custom_file_name = file_names[index - 1] if file_names else None
            saved_paths.append(
                self._download_image(
                    image_url=image_url,
                    output_dir=save_dir,
                    index=index,
                    file_name_prefix=resolved_prefix,
                    file_name=custom_file_name,
                )
            )
        return saved_paths

    def generate_and_save(
        self,
        prompt: str,
        output_dir: str | Path,
        *,
        reference_images: list[str | dict[str, str]] | None = None,
        image_count: int = 1,
        model_name: str | None = None,
        response_format: str | None = None,
        size: str | None = None,
        stream: bool | None = None,
        watermark: bool | None = None,
        sequential_image_generation: str | None = None,
        file_name_prefix: str | None = None,
        file_names: list[str] | None = None,
        strict_image_count: bool | None = None,
        retry_on_partial: bool | None = None,
        max_partial_retries: int | None = None,
        **extra_body: Any,
    ) -> list[Path]:
        """生成图片并保存到本地目录。"""

        image_urls = self.generate_image_urls(
            prompt=prompt,
            reference_images=reference_images,
            image_count=image_count,
            model_name=model_name,
            response_format=response_format,
            size=size,
            stream=stream,
            watermark=watermark,
            sequential_image_generation=sequential_image_generation,
            strict_image_count=strict_image_count,
            retry_on_partial=retry_on_partial,
            max_partial_retries=max_partial_retries,
            **extra_body,
        )
        return self.save_images(
            image_urls=image_urls,
            output_dir=output_dir,
            file_name_prefix=file_name_prefix,
            file_names=file_names,
        )

    def generate_and_save_single(
        self,
        prompt: str,
        output_dir: str | Path,
        *,
        reference_images: list[str | dict[str, str]] | None = None,
        model_name: str | None = None,
        response_format: str | None = None,
        size: str | None = None,
        watermark: bool | None = None,
        file_name: str | None = None,
        file_name_prefix: str | None = None,
        strict_image_count: bool | None = None,
        retry_on_partial: bool | None = None,
        max_partial_retries: int | None = None,
        **extra_body: Any,
    ) -> Path:
        """生成单张图片并保存到本地。"""

        saved_paths = self.generate_and_save(
            prompt=prompt,
            output_dir=output_dir,
            reference_images=reference_images,
            image_count=1,
            model_name=model_name,
            response_format=response_format,
            size=size,
            stream=False,
            watermark=watermark,
            sequential_image_generation="disabled",
            file_name_prefix=file_name_prefix,
            file_names=[file_name] if file_name else None,
            strict_image_count=strict_image_count,
            retry_on_partial=retry_on_partial,
            max_partial_retries=max_partial_retries,
            **extra_body,
        )
        if len(saved_paths) != 1:
            raise SeedImageAPIError(f"预期保存 1 张图片，实际保存 {len(saved_paths)} 张。")
        return saved_paths[0]

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

    def _validate_generated_image_count(
        self,
        *,
        expected_image_count: int,
        actual_image_count: int,
        strict_image_count: bool,
    ) -> None:
        if not strict_image_count:
            return

        if actual_image_count < expected_image_count:
            raise SeedImageAPIError(
                f"预期生成 {expected_image_count} 张图片，接口实际仅返回 {actual_image_count} 张。"
                "这通常表示上游任务部分成功，可尝试优化提示词，或增大 max_partial_retries 后重试。"
            )

    def _download_image(
        self,
        *,
        image_url: str,
        output_dir: Path,
        index: int,
        file_name_prefix: str,
        file_name: str | None,
    ) -> Path:
        if not image_url.strip():
            raise SeedImageAPIError("待下载图片 URL 不能为空。")

        download_request = request.Request(
            url=image_url,
            headers={"User-Agent": "SeedImageClient/1.0"},
            method="GET",
        )

        try:
            with request.urlopen(download_request, timeout=self.timeout) as response:
                image_bytes = response.read()
                content_type = response.headers.get("Content-Type", "")
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise SeedImageAPIError(f"下载图片失败，HTTP {exc.code}: {detail}") from exc
        except error.URLError as exc:
            raise SeedImageAPIError(f"下载图片网络异常: {exc}") from exc

        suffix = self._resolve_file_suffix(
            image_url=image_url,
            image_bytes=image_bytes,
            content_type=content_type,
            file_name=file_name,
        )
        target_file_name = file_name or f"{file_name_prefix}_{index:02d}{suffix}"
        target_path = output_dir / target_file_name

        try:
            target_path.write_bytes(image_bytes)
        except OSError as exc:
            raise SeedImageAPIError(f"写入图片文件失败: {target_path}") from exc

        return target_path

    def _resolve_file_suffix(
        self,
        *,
        image_url: str,
        image_bytes: bytes,
        content_type: str,
        file_name: str | None,
    ) -> str:
        if file_name:
            suffix = Path(file_name).suffix
            if suffix:
                return suffix

        mime_type = content_type.split(";", 1)[0].strip() if content_type else ""
        if mime_type.startswith("image/"):
            guessed_suffix = mimetypes.guess_extension(mime_type)
            if guessed_suffix:
                return guessed_suffix

        inferred_mime_type = self._infer_mime_type(image_bytes)
        guessed_suffix = mimetypes.guess_extension(inferred_mime_type)
        if guessed_suffix:
            return guessed_suffix

        url_suffix = Path(parse.urlparse(image_url).path).suffix
        if url_suffix:
            return url_suffix

        return ".png"

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

    def _extract_generated_image_count(
        self,
        response: dict[str, Any] | list[dict[str, Any]],
    ) -> int | None:
        if isinstance(response, dict):
            usage = response.get("usage")
            if isinstance(usage, dict):
                generated_images = usage.get("generated_images")
                if isinstance(generated_images, int):
                    return generated_images

        if isinstance(response, list):
            for event in response:
                if not isinstance(event, dict):
                    continue
                data = event.get("data")
                if not isinstance(data, dict):
                    continue
                usage = data.get("usage")
                if not isinstance(usage, dict):
                    continue
                generated_images = usage.get("generated_images")
                if isinstance(generated_images, int):
                    return generated_images

        return None

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

    def _apply_config_defaults(self) -> None:
        try:
            config = load_seed_section("image", self.params_config_path)
        except Exception as exc:
            raise SeedImageAPIError(str(exc)) from exc

        self.model_name = self.model_name or str(config.get("model_name") or DEFAULT_IMAGE_MODEL_NAME)
        if self.timeout is None:
            self.timeout = int(config.get("timeout") or 300)
        self.response_format = self.response_format or str(config.get("response_format") or "url")
        self.size = self.size or str(config.get("size") or "2K")
        if self.stream is None:
            self.stream = config.get("stream")
        if self.watermark is None:
            self.watermark = bool(config.get("watermark", True))
        if self.sequential_image_generation is None:
            self.sequential_image_generation = config.get("sequential_image_generation")
        if self.strict_image_count is None:
            self.strict_image_count = bool(config.get("strict_image_count", True))
        if self.retry_on_partial is None:
            self.retry_on_partial = bool(config.get("retry_on_partial", True))
        if self.max_partial_retries is None:
            self.max_partial_retries = int(config.get("max_partial_retries", 3))

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
