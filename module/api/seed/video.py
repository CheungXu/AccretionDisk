"""字节 Seed 视频生成接口。"""

from __future__ import annotations

import base64
import binascii
import json
import mimetypes
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib import error, parse, request

from .config import load_api_key, load_seed_section


DEFAULT_VIDEO_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks"
DEFAULT_VIDEO_MODEL_NAME = "doubao-seedance-1-5-pro-251215"
DEFAULT_IMAGE_MIME_TYPE = "image/jpeg"
DEFAULT_DOWNLOAD_PREFIX = "seed_video"
DEFAULT_POLL_INTERVAL_SECONDS = 5
DEFAULT_WAIT_TIMEOUT_SECONDS = 900
TERMINAL_TASK_STATUSES = {"succeeded", "failed", "canceled", "cancelled"}
SUCCESS_TASK_STATUSES = {"succeeded"}
FAILURE_TASK_STATUSES = {"failed", "canceled", "cancelled"}


class SeedVideoAPIError(RuntimeError):
    """Seed 视频生成接口请求异常。"""


@dataclass
class SeedVideoClient:
    """字节 Seed 视频生成客户端。"""

    api_key: str | None = None
    model_name: str | None = None
    base_url: str = DEFAULT_VIDEO_BASE_URL
    timeout: int | None = None
    config_path: str | Path | None = None
    params_config_path: str | Path | None = None
    default_image_mime_type: str = DEFAULT_IMAGE_MIME_TYPE
    default_download_prefix: str = DEFAULT_DOWNLOAD_PREFIX
    default_task_type: str | None = None
    default_image_role: str | None = None
    generate_audio: bool | None = None
    default_prompt_options: dict[str, Any] | None = None
    poll_interval_seconds: int | None = None
    wait_timeout_seconds: int | None = None
    default_request_options: dict[str, Any] | None = None
    default_headers: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self._apply_config_defaults()
        if self.api_key is None:
            self.api_key = load_api_key(self.config_path)
        if not self.api_key:
            raise SeedVideoAPIError(
                "缺少 API Key，请先设置 ARK_API_KEY，或在 config/seed_key.json 中配置 api_key。"
            )

    def create_task(
        self,
        content: list[dict[str, Any] | str],
        *,
        model_name: str | None = None,
        **extra_body: Any,
    ) -> dict[str, Any]:
        """创建视频生成任务。"""

        request_options = dict(self.default_request_options or {})
        if self.generate_audio is not None and "generate_audio" not in request_options:
            request_options["generate_audio"] = self.generate_audio
        request_options.update(extra_body)
        request_payload = self._build_task_payload(
            content=content,
            model_name=model_name or self.model_name,
            extra_body=request_options,
        )
        return self._request_json("POST", self.base_url, payload=request_payload)

    def create_text_to_video_task(
        self,
        prompt: str,
        *,
        prompt_options: dict[str, Any] | None = None,
        model_name: str | None = None,
        **extra_body: Any,
    ) -> dict[str, Any]:
        """创建文生视频任务。"""

        content = [
            {
                "type": "text",
                "text": self._build_prompt_text(
                    prompt,
                    prompt_options=self._merge_prompt_options(prompt_options),
                ),
            }
        ]
        return self.create_task(
            content=content,
            model_name=model_name,
            **extra_body,
        )

    def create_image_to_video_task(
        self,
        prompt: str,
        image_input: str | dict[str, str],
        *,
        image_role: str | None = None,
        prompt_options: dict[str, Any] | None = None,
        model_name: str | None = None,
        **extra_body: Any,
    ) -> dict[str, Any]:
        """创建图生视频任务。"""

        normalized_image_url = self._normalize_image_input(image_input)
        content = [
            {
                "type": "text",
                "text": self._build_prompt_text(
                    prompt,
                    prompt_options=self._merge_prompt_options(prompt_options),
                ),
            },
            {
                "type": "image_url",
                "image_url": {"url": normalized_image_url},
                "role": image_role or self.default_image_role,
            },
        ]
        return self.create_task(
            content=content,
            model_name=model_name,
            task_type=extra_body.pop("task_type", self.default_task_type),
            **extra_body,
        )

    def get_task(self, task_id: str) -> dict[str, Any]:
        """查询单个视频生成任务。"""

        normalized_task_id = task_id.strip()
        if not normalized_task_id:
            raise SeedVideoAPIError("task_id 不能为空。")

        task_url = f"{self.base_url}/{parse.quote(normalized_task_id)}"
        try:
            return self._request_json("GET", task_url)
        except SeedVideoAPIError as exc:
            # 不同文档页面对查询接口的资源形式描述不够统一，404 时回退到 query 参数形式。
            if "HTTP 404" not in str(exc):
                raise

        fallback_url = f"{self.base_url}?id={parse.quote(normalized_task_id)}"
        return self._request_json("GET", fallback_url)

    def wait_for_task(
        self,
        task_id: str,
        *,
        poll_interval_seconds: int | None = None,
        timeout_seconds: int | None = None,
    ) -> dict[str, Any]:
        """轮询等待任务结束，并返回最终任务结果。"""

        poll_interval_seconds = poll_interval_seconds or self.poll_interval_seconds
        timeout_seconds = timeout_seconds or self.wait_timeout_seconds
        if poll_interval_seconds <= 0:
            raise SeedVideoAPIError("poll_interval_seconds 必须大于 0。")
        if timeout_seconds <= 0:
            raise SeedVideoAPIError("timeout_seconds 必须大于 0。")

        deadline = time.time() + timeout_seconds
        last_response: dict[str, Any] | None = None

        while time.time() < deadline:
            last_response = self.get_task(task_id)
            task_status = self.extract_task_status(last_response)
            if task_status in TERMINAL_TASK_STATUSES:
                if task_status in FAILURE_TASK_STATUSES:
                    raise SeedVideoAPIError(
                        f"视频生成任务结束但状态异常: {task_status}"
                    )
                return last_response
            time.sleep(poll_interval_seconds)

        raise SeedVideoAPIError(
            f"等待视频任务超时，task_id={task_id}，最后状态={self.extract_task_status(last_response) if last_response else 'unknown'}。"
        )

    def create_and_wait(
        self,
        content: list[dict[str, Any] | str],
        *,
        model_name: str | None = None,
        poll_interval_seconds: int | None = None,
        timeout_seconds: int | None = None,
        **extra_body: Any,
    ) -> dict[str, Any]:
        """创建任务并等待任务完成。"""

        task_response = self.create_task(
            content=content,
            model_name=model_name,
            **extra_body,
        )
        task_id = self.extract_task_id(task_response)
        return self.wait_for_task(
            task_id,
            poll_interval_seconds=poll_interval_seconds,
            timeout_seconds=timeout_seconds,
        )

    def create_image_to_video_and_wait(
        self,
        prompt: str,
        image_input: str | dict[str, str],
        *,
        image_role: str | None = None,
        prompt_options: dict[str, Any] | None = None,
        model_name: str | None = None,
        poll_interval_seconds: int | None = None,
        timeout_seconds: int | None = None,
        **extra_body: Any,
    ) -> dict[str, Any]:
        """创建图生视频任务并等待完成。"""

        task_response = self.create_image_to_video_task(
            prompt=prompt,
            image_input=image_input,
            image_role=image_role,
            prompt_options=prompt_options,
            model_name=model_name,
            **extra_body,
        )
        task_id = self.extract_task_id(task_response)
        return self.wait_for_task(
            task_id,
            poll_interval_seconds=poll_interval_seconds,
            timeout_seconds=timeout_seconds,
        )

    def save_videos(
        self,
        video_urls: list[str],
        output_dir: str | Path,
        *,
        file_name_prefix: str | None = None,
        file_names: list[str] | None = None,
    ) -> list[Path]:
        """将视频 URL 下载到本地目录。"""

        if not video_urls:
            raise SeedVideoAPIError("video_urls 不能为空。")

        save_dir = Path(output_dir).expanduser()
        save_dir.mkdir(parents=True, exist_ok=True)

        if file_names is not None and len(file_names) != len(video_urls):
            raise SeedVideoAPIError("file_names 数量必须与 video_urls 数量一致。")

        resolved_prefix = file_name_prefix or self.default_download_prefix
        saved_paths: list[Path] = []
        for index, video_url in enumerate(video_urls, start=1):
            custom_file_name = file_names[index - 1] if file_names else None
            saved_paths.append(
                self._download_video(
                    video_url=video_url,
                    output_dir=save_dir,
                    index=index,
                    file_name_prefix=resolved_prefix,
                    file_name=custom_file_name,
                )
            )
        return saved_paths

    def save_videos_from_response(
        self,
        response: dict[str, Any],
        output_dir: str | Path,
        *,
        file_name_prefix: str | None = None,
        file_names: list[str] | None = None,
    ) -> list[Path]:
        """从任务结果中提取视频 URL 并保存到本地。"""

        video_urls = self.extract_video_urls(response)
        return self.save_videos(
            video_urls=video_urls,
            output_dir=output_dir,
            file_name_prefix=file_name_prefix,
            file_names=file_names,
        )

    def create_image_to_video_and_save(
        self,
        prompt: str,
        image_input: str | dict[str, str],
        output_dir: str | Path,
        *,
        image_role: str | None = None,
        prompt_options: dict[str, Any] | None = None,
        model_name: str | None = None,
        poll_interval_seconds: int | None = None,
        timeout_seconds: int | None = None,
        file_name_prefix: str | None = None,
        file_name: str | None = None,
        **extra_body: Any,
    ) -> list[Path]:
        """创建图生视频任务，等待完成后保存到本地。"""

        final_response = self.create_image_to_video_and_wait(
            prompt=prompt,
            image_input=image_input,
            image_role=image_role,
            prompt_options=prompt_options,
            model_name=model_name,
            poll_interval_seconds=poll_interval_seconds,
            timeout_seconds=timeout_seconds,
            **extra_body,
        )
        return self.save_videos_from_response(
            response=final_response,
            output_dir=output_dir,
            file_name_prefix=file_name_prefix,
            file_names=[file_name] if file_name else None,
        )

    @staticmethod
    def extract_task_id(response: dict[str, Any]) -> str:
        """从任务响应中提取任务 ID。"""

        candidate_keys = ("id", "task_id")
        for key in candidate_keys:
            task_id = response.get(key)
            if isinstance(task_id, str) and task_id.strip():
                return task_id

        data = response.get("data")
        if isinstance(data, dict):
            for key in candidate_keys:
                task_id = data.get(key)
                if isinstance(task_id, str) and task_id.strip():
                    return task_id

        raise SeedVideoAPIError("未能从响应中提取任务 ID。")

    @staticmethod
    def extract_task_status(response: dict[str, Any] | None) -> str:
        """从任务响应中提取状态。"""

        if not isinstance(response, dict):
            return "unknown"

        candidate_keys = ("status", "state")
        for key in candidate_keys:
            status = response.get(key)
            if isinstance(status, str) and status.strip():
                return status.strip().lower()

        data = response.get("data")
        if isinstance(data, dict):
            for key in candidate_keys:
                status = data.get(key)
                if isinstance(status, str) and status.strip():
                    return status.strip().lower()

        return "unknown"

    @staticmethod
    def extract_video_urls(response: dict[str, Any]) -> list[str]:
        """从任务响应中提取视频 URL。"""

        video_urls: list[str] = []
        seen_urls: set[str] = set()

        def walk(node: Any) -> None:
            if isinstance(node, dict):
                for key, value in node.items():
                    if key in {"url", "video_url"} and isinstance(value, str) and value.strip():
                        normalized_value = value.strip()
                        if normalized_value not in seen_urls:
                            seen_urls.add(normalized_value)
                            video_urls.append(normalized_value)
                    else:
                        walk(value)
                return

            if isinstance(node, list):
                for item in node:
                    walk(item)

        walk(response)
        return video_urls

    def _download_video(
        self,
        *,
        video_url: str,
        output_dir: Path,
        index: int,
        file_name_prefix: str,
        file_name: str | None,
    ) -> Path:
        if not video_url.strip():
            raise SeedVideoAPIError("待下载视频 URL 不能为空。")

        download_request = request.Request(
            url=video_url,
            headers={"User-Agent": "SeedVideoClient/1.0"},
            method="GET",
        )

        try:
            with request.urlopen(download_request, timeout=self.timeout) as response:
                video_bytes = response.read()
                content_type = response.headers.get("Content-Type", "")
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise SeedVideoAPIError(f"下载视频失败，HTTP {exc.code}: {detail}") from exc
        except error.URLError as exc:
            raise SeedVideoAPIError(f"下载视频网络异常: {exc}") from exc

        suffix = self._resolve_video_file_suffix(
            video_url=video_url,
            content_type=content_type,
            file_name=file_name,
        )
        target_file_name = file_name or f"{file_name_prefix}_{index:02d}{suffix}"
        target_path = output_dir / target_file_name

        try:
            target_path.write_bytes(video_bytes)
        except OSError as exc:
            raise SeedVideoAPIError(f"写入视频文件失败: {target_path}") from exc

        return target_path

    def _resolve_video_file_suffix(
        self,
        *,
        video_url: str,
        content_type: str,
        file_name: str | None,
    ) -> str:
        if file_name:
            suffix = Path(file_name).suffix
            if suffix:
                return suffix

        mime_type = content_type.split(";", 1)[0].strip() if content_type else ""
        if mime_type.startswith("video/"):
            guessed_suffix = mimetypes.guess_extension(mime_type)
            if guessed_suffix:
                return guessed_suffix

        url_suffix = Path(parse.urlparse(video_url).path).suffix
        if url_suffix:
            return url_suffix

        return ".mp4"

    def _build_task_payload(
        self,
        *,
        content: list[dict[str, Any] | str],
        model_name: str,
        extra_body: dict[str, Any],
    ) -> dict[str, Any]:
        normalized_content = self._normalize_content(content)
        request_payload: dict[str, Any] = {
            "model": model_name,
            "content": normalized_content,
        }
        request_payload.update(extra_body)
        return request_payload

    def _normalize_content(
        self,
        content: list[dict[str, Any] | str],
    ) -> list[dict[str, Any]]:
        if not content:
            raise SeedVideoAPIError("content 不能为空。")

        normalized_content: list[dict[str, Any]] = []
        for content_item in content:
            if isinstance(content_item, str):
                normalized_content.append({"type": "text", "text": content_item})
                continue
            if isinstance(content_item, dict):
                normalized_content.append(self._normalize_content_item(content_item))
                continue
            raise SeedVideoAPIError("content 中存在不支持的内容项类型。")
        return normalized_content

    def _normalize_content_item(self, content_item: dict[str, Any]) -> dict[str, Any]:
        content_type = content_item.get("type")

        if content_type in {None, "text"}:
            text = content_item.get("text")
            if not isinstance(text, str) or not text.strip():
                raise SeedVideoAPIError("文本内容项缺少有效 text。")
            return {
                "type": "text",
                "text": text,
            }

        if content_type in {"image_url", "image"}:
            image_role = content_item.get("role", "reference_image")
            image_url_payload = content_item.get("image_url")
            if isinstance(image_url_payload, dict):
                image_value = image_url_payload.get("url")
            else:
                image_value = (
                    content_item.get("image_path")
                    or content_item.get("image_base64")
                    or image_url_payload
                )

            if image_value is None:
                raise SeedVideoAPIError("图片内容项缺少图片数据。")

            if "image_base64" in content_item:
                normalized_image_url = self._normalize_image_dict(
                    {
                        "image_base64": str(content_item["image_base64"]),
                        "mime_type": str(
                            content_item.get("mime_type") or self.default_image_mime_type
                        ),
                    }
                )
            elif "image_path" in content_item:
                normalized_image_url = self._normalize_image_dict(
                    {"image_path": str(content_item["image_path"])}
                )
            else:
                normalized_image_url = self._normalize_image_input(str(image_value))

            return {
                "type": "image_url",
                "image_url": {"url": normalized_image_url},
                "role": image_role,
            }

        raise SeedVideoAPIError(f"不支持的内容类型: {content_type}")

    def _build_prompt_text(
        self,
        prompt: str,
        *,
        prompt_options: dict[str, Any] | None,
    ) -> str:
        if not prompt.strip():
            raise SeedVideoAPIError("prompt 不能为空。")

        if not prompt_options:
            return prompt

        option_segments: list[str] = []
        # 使用命令行风格的附加参数，与官方示例保持一致。
        for option_name, option_value in prompt_options.items():
            if option_value is None:
                continue
            normalized_name = str(option_name).strip()
            if not normalized_name:
                continue

            if isinstance(option_value, bool):
                normalized_value = str(option_value).lower()
            else:
                normalized_value = str(option_value).strip()
            option_segments.append(f"--{normalized_name} {normalized_value}")

        if not option_segments:
            return prompt
        return f"{prompt} {' '.join(option_segments)}"

    def _merge_prompt_options(
        self,
        prompt_options: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        resolved_prompt_options = dict(self.default_prompt_options or {})
        if prompt_options:
            resolved_prompt_options.update(prompt_options)
        return resolved_prompt_options or None

    def _normalize_image_input(self, image_input: str | dict[str, str]) -> str:
        if isinstance(image_input, dict):
            return self._normalize_image_dict(image_input)

        if not isinstance(image_input, str):
            raise SeedVideoAPIError("图片输入类型不受支持。")

        normalized_input = image_input.strip()
        if not normalized_input:
            raise SeedVideoAPIError("图片输入不能为空。")

        if self._is_http_url(normalized_input):
            return normalized_input
        if self._is_data_uri(normalized_input):
            return normalized_input

        local_path = Path(normalized_input).expanduser()
        if local_path.exists() and local_path.is_file():
            return self._encode_local_image_to_data_uri(local_path)

        return self._encode_base64_to_data_uri(normalized_input)

    def _normalize_image_dict(self, image_input: dict[str, str]) -> str:
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

        raise SeedVideoAPIError(
            "图片字典输入必须包含 image_url、image_path 或 image_base64 之一。"
        )

    def _encode_local_image_to_data_uri(self, image_path: Path) -> str:
        if not image_path.exists() or not image_path.is_file():
            raise SeedVideoAPIError(f"本地图片不存在: {image_path}")

        try:
            image_bytes = image_path.read_bytes()
        except OSError as exc:
            raise SeedVideoAPIError(f"读取本地图片失败: {image_path}") from exc

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
            raise SeedVideoAPIError("Base64 图片内容不能为空。")

        try:
            image_bytes = base64.b64decode(normalized_base64, validate=True)
        except binascii.Error as exc:
            raise SeedVideoAPIError("Base64 图片内容不合法。") from exc

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
            config = load_seed_section("video", self.params_config_path)
        except Exception as exc:
            raise SeedVideoAPIError(str(exc)) from exc

        self.model_name = self.model_name or str(config.get("model_name") or DEFAULT_VIDEO_MODEL_NAME)
        if self.timeout is None:
            self.timeout = int(config.get("timeout") or 300)
        self.default_task_type = self.default_task_type or str(config.get("task_type") or "i2v")
        self.default_image_role = self.default_image_role or str(config.get("image_role") or "first_frame")
        if self.generate_audio is None:
            configured_generate_audio = config.get("generate_audio")
            self.generate_audio = True if configured_generate_audio is None else bool(configured_generate_audio)
        if self.poll_interval_seconds is None:
            self.poll_interval_seconds = int(
                config.get("poll_interval_seconds") or DEFAULT_POLL_INTERVAL_SECONDS
            )
        if self.wait_timeout_seconds is None:
            self.wait_timeout_seconds = int(
                config.get("wait_timeout_seconds") or DEFAULT_WAIT_TIMEOUT_SECONDS
            )
        if self.default_prompt_options is None:
            default_prompt_options = config.get("default_prompt_options", {})
            if not isinstance(default_prompt_options, dict):
                raise SeedVideoAPIError("video.default_prompt_options 配置必须为对象。")
            self.default_prompt_options = default_prompt_options
        if self.default_request_options is None:
            default_request_options = config.get("default_request_options", {})
            if not isinstance(default_request_options, dict):
                raise SeedVideoAPIError("video.default_request_options 配置必须为对象。")
            self.default_request_options = default_request_options

    def _request_json(
        self,
        method: str,
        url: str,
        *,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        request_headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        request_headers.update(self.default_headers)

        request_data = None
        if payload is not None:
            request_data = json.dumps(payload).encode("utf-8")

        http_request = request.Request(
            url=url,
            data=request_data,
            headers=request_headers,
            method=method,
        )

        try:
            with request.urlopen(http_request, timeout=self.timeout) as response:
                raw_response_text = response.read().decode("utf-8")
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise SeedVideoAPIError(f"Seed 视频接口请求失败，HTTP {exc.code}: {detail}") from exc
        except error.URLError as exc:
            raise SeedVideoAPIError(f"Seed 视频接口网络异常: {exc}") from exc

        try:
            return json.loads(raw_response_text)
        except json.JSONDecodeError as exc:
            raise SeedVideoAPIError(
                f"Seed 视频接口返回非 JSON 内容: {raw_response_text}"
            ) from exc
