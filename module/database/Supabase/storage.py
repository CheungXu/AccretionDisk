"""Supabase Storage 工具。"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib import parse, request as urllib_request, error as urllib_error

from .client import SupabaseClientFactory, SupabaseClientError, SupabaseRestClient
from .config import (
    SupabaseStorageConfig,
    load_supabase_storage_config,
    normalize_path_segment,
    normalize_optional_str,
)

TUS_CHUNK_SIZE = 6 * 1024 * 1024
TUS_THRESHOLD = 20 * 1024 * 1024


@dataclass(frozen=True)
class SupabaseStorageObjectRef:
    """Storage 对象引用。"""

    bucket_name: str
    object_path: str

    @property
    def object_name(self) -> str:
        """返回 bucket 内对象路径。"""

        return self.object_path


@dataclass
class SupabaseStorageService:
    """基于 REST 接口的 Supabase Storage 服务。"""

    client: SupabaseRestClient
    storage_config: SupabaseStorageConfig

    @property
    def bucket_name(self) -> str:
        """返回默认 bucket 名称。"""

        return self.storage_config.bucket_name

    def build_project_prefix(self, project_id: str) -> str:
        """构造项目根路径前缀。"""

        normalized_project_id = normalize_path_segment(project_id)
        if not normalized_project_id:
            raise SupabaseClientError("project_id 不能为空。")
        return self.storage_config.build_prefixed_path(normalized_project_id)

    def build_asset_object_path(
        self,
        *,
        project_id: str,
        asset_type: str,
        asset_id: str,
        file_name: str,
    ) -> str:
        """构造资产对象路径。"""

        return self._build_project_object_path(
            project_id,
            "assets",
            normalize_path_segment(asset_type) or "misc",
            normalize_path_segment(asset_id) or "asset",
            normalize_path_segment(file_name) or "file.bin",
        )

    def build_snapshot_object_path(
        self,
        *,
        project_id: str,
        snapshot_type: str,
        file_name: str,
    ) -> str:
        """构造快照对象路径。"""

        return self._build_project_object_path(
            project_id,
            "snapshots",
            normalize_path_segment(snapshot_type) or "snapshot",
            normalize_path_segment(file_name) or "snapshot.json",
        )

    def build_log_object_path(
        self,
        *,
        project_id: str,
        run_id: str,
        file_name: str | None = None,
    ) -> str:
        """构造日志对象路径。"""

        normalized_run_id = normalize_path_segment(run_id) or "run"
        normalized_file_name = normalize_path_segment(file_name) or f"{normalized_run_id}.log"
        return self._build_project_object_path(
            project_id,
            "logs",
            normalized_run_id,
            normalized_file_name,
        )

    def build_export_object_path(
        self,
        *,
        project_id: str,
        export_name: str,
        file_name: str,
    ) -> str:
        """构造导出对象路径。"""

        return self._build_project_object_path(
            project_id,
            "exports",
            normalize_path_segment(export_name) or "export",
            normalize_path_segment(file_name) or "artifact.bin",
        )

    def build_public_url(self, object_path: str) -> str:
        """构造 public bucket 访问 URL。"""

        quoted_path = self._quote_object_path(object_path)
        return f"{self.client.storage_base_url}/object/public/{self.bucket_name}/{quoted_path}"

    def list_buckets(self) -> list[dict[str, Any]]:
        """查询 bucket 列表。"""

        response = self.client.request_json(
            "GET",
            "/bucket",
            base_path="storage",
            bearer_token=self._resolve_storage_bearer_token(None),
        )
        return response if isinstance(response, list) else []

    def create_bucket(self, *, public: bool | None = None) -> dict[str, Any]:
        """创建默认 bucket。"""

        response = self.client.request_json(
            "POST",
            "/bucket",
            base_path="storage",
            bearer_token=self._resolve_storage_bearer_token(None),
            body={
                "id": self.bucket_name,
                "name": self.bucket_name,
                "public": self.storage_config.public_bucket if public is None else public,
            },
        )
        return response if isinstance(response, dict) else {"response": response}

    def ensure_bucket_exists(self) -> dict[str, Any]:
        """确保默认 bucket 已存在。"""

        buckets = self.list_buckets()
        for item in buckets:
            if not isinstance(item, dict):
                continue
            if item.get("id") == self.bucket_name or item.get("name") == self.bucket_name:
                return item
        return self.create_bucket()

    def upload_bytes(
        self,
        *,
        object_path: str,
        content: bytes,
        content_type: str = "application/octet-stream",
        upsert: bool = False,
        bearer_token: str | None = None,
    ) -> dict[str, Any]:
        """上传字节内容。超过阈值自动走 TUS 分片上传。"""

        if len(content) > TUS_THRESHOLD:
            return self._upload_bytes_tus(
                object_path=object_path,
                content=content,
                content_type=content_type,
                upsert=upsert,
                bearer_token=bearer_token,
            )

        normalized_path = self._normalize_required_object_path(object_path)
        raw_response = self.client.request_bytes(
            "POST",
            f"/object/{self.bucket_name}/{self._quote_object_path(normalized_path)}",
            base_path="storage",
            body_bytes=content,
            bearer_token=self._resolve_storage_bearer_token(bearer_token),
            extra_headers={
                "Content-Type": content_type,
                "x-upsert": "true" if upsert else "false",
            },
        )
        if not raw_response:
            return {
                "bucket_name": self.bucket_name,
                "object_path": normalized_path,
            }
        try:
            return json.loads(raw_response.decode("utf-8"))
        except json.JSONDecodeError:
            return {
                "bucket_name": self.bucket_name,
                "object_path": normalized_path,
                "raw_response": raw_response.decode("utf-8", errors="replace"),
            }

    def upload_text(
        self,
        *,
        object_path: str,
        content: str,
        content_type: str = "application/json; charset=utf-8",
        upsert: bool = True,
        bearer_token: str | None = None,
    ) -> dict[str, Any]:
        """上传文本内容。"""

        return self.upload_bytes(
            object_path=object_path,
            content=content.encode("utf-8"),
            content_type=content_type,
            upsert=upsert,
            bearer_token=bearer_token,
        )

    def upload_file(
        self,
        *,
        file_path: str | Path,
        object_path: str,
        content_type: str | None = None,
        upsert: bool = False,
        bearer_token: str | None = None,
    ) -> dict[str, Any]:
        """上传本地文件。超过阈值自动走 TUS 分片上传。"""

        path = Path(file_path)
        file_size = path.stat().st_size
        normalized_content_type = normalize_optional_str(content_type) or "application/octet-stream"

        if file_size > TUS_THRESHOLD:
            return self._upload_file_tus(
                file_path=path,
                object_path=object_path,
                content_type=normalized_content_type,
                upsert=upsert,
                bearer_token=bearer_token,
            )

        data = path.read_bytes()
        return self.upload_bytes(
            object_path=object_path,
            content=data,
            content_type=normalized_content_type,
            upsert=upsert,
            bearer_token=bearer_token,
        )

    def _upload_file_tus(
        self,
        *,
        file_path: Path,
        object_path: str,
        content_type: str = "application/octet-stream",
        upsert: bool = False,
        bearer_token: str | None = None,
    ) -> dict[str, Any]:
        """通过 TUS 分片上传协议上传大文件。"""

        normalized_path = self._normalize_required_object_path(object_path)
        file_size = file_path.stat().st_size
        token = self._resolve_storage_bearer_token(bearer_token)

        b64_bucket = base64.b64encode(self.bucket_name.encode()).decode()
        b64_object = base64.b64encode(normalized_path.encode()).decode()
        b64_ct = base64.b64encode(content_type.encode()).decode()

        create_url = f"{self.client.storage_base_url}/upload/resumable"
        create_headers = {
            "apikey": self.client.api_key,
            "Authorization": f"Bearer {token}",
            "x-upsert": "true" if upsert else "false",
            "Upload-Length": str(file_size),
            "Upload-Metadata": f"bucketName {b64_bucket},objectName {b64_object},contentType {b64_ct}",
            "Tus-Resumable": "1.0.0",
        }
        req = urllib_request.Request(create_url, method="POST", headers=create_headers)
        try:
            with urllib_request.urlopen(req, timeout=self.client.timeout_seconds) as resp:
                location = resp.headers.get("Location")
        except urllib_error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace") if exc.fp else str(exc)
            raise SupabaseClientError(
                f"TUS 创建上传会话失败: HTTP {exc.code}，{details}",
                status_code=exc.code,
            ) from exc

        if not location:
            raise SupabaseClientError("TUS 创建成功但未返回 Location。")

        offset = 0
        with open(file_path, "rb") as f:
            while offset < file_size:
                chunk = f.read(TUS_CHUNK_SIZE)
                chunk_len = len(chunk)
                patch_headers = {
                    "apikey": self.client.api_key,
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/offset+octet-stream",
                    "Upload-Offset": str(offset),
                    "Tus-Resumable": "1.0.0",
                    "Content-Length": str(chunk_len),
                }
                patch_req = urllib_request.Request(location, data=chunk, method="PATCH", headers=patch_headers)
                try:
                    with urllib_request.urlopen(patch_req, timeout=self.client.timeout_seconds) as resp:
                        offset = int(resp.headers.get("Upload-Offset", offset + chunk_len))
                except urllib_error.HTTPError as exc:
                    details = exc.read().decode("utf-8", errors="replace") if exc.fp else str(exc)
                    raise SupabaseClientError(
                        f"TUS 分片上传失败 (offset={offset}): HTTP {exc.code}，{details}",
                        status_code=exc.code,
                    ) from exc

        return {
            "bucket_name": self.bucket_name,
            "object_path": normalized_path,
            "upload_method": "tus",
            "total_bytes": file_size,
        }

    def download_object(
        self,
        *,
        object_path: str,
        bearer_token: str | None = None,
    ) -> bytes:
        """下载私有对象。"""

        normalized_path = self._normalize_required_object_path(object_path)
        return self.client.request_bytes(
            "GET",
            f"/object/authenticated/{self.bucket_name}/{self._quote_object_path(normalized_path)}",
            base_path="storage",
            bearer_token=self._resolve_storage_bearer_token(bearer_token),
        )

    def create_signed_url(
        self,
        *,
        object_path: str,
        expires_in: int | None = None,
        bearer_token: str | None = None,
    ) -> str:
        """为私有对象生成临时下载链接。"""

        normalized_path = self._normalize_required_object_path(object_path)
        ttl = expires_in or self.storage_config.signed_url_ttl_seconds
        response = self.client.request_json(
            "POST",
            f"/object/sign/{self.bucket_name}/{self._quote_object_path(normalized_path)}",
            base_path="storage",
            bearer_token=self._resolve_storage_bearer_token(bearer_token),
            body={"expiresIn": ttl},
        )
        if not isinstance(response, dict):
            raise SupabaseClientError("生成 signed URL 失败，返回结构不是字典。", payload=response)
        signed_url = normalize_optional_str(response.get("signedURL"))
        if not signed_url:
            raise SupabaseClientError("生成 signed URL 失败，响应中缺少 signedURL。", payload=response)
        if signed_url.startswith("http://") or signed_url.startswith("https://"):
            return signed_url
        return f"{self.client.storage_base_url}{signed_url}"

    def remove_objects(
        self,
        *,
        object_paths: list[str],
        bearer_token: str | None = None,
    ) -> dict[str, Any]:
        """批量删除对象。"""

        normalized_paths = [
            self._normalize_required_object_path(item)
            for item in object_paths
            if normalize_path_segment(item)
        ]
        if not normalized_paths:
            return {"deleted": []}
        response = self.client.request_json(
            "DELETE",
            f"/object/{self.bucket_name}",
            base_path="storage",
            bearer_token=self._resolve_storage_bearer_token(bearer_token),
            body={"prefixes": normalized_paths},
        )
        return response if isinstance(response, dict) else {"response": response}

    def _upload_bytes_tus(
        self,
        *,
        object_path: str,
        content: bytes,
        content_type: str = "application/octet-stream",
        upsert: bool = False,
        bearer_token: str | None = None,
    ) -> dict[str, Any]:
        """将大字节内容写入临时文件后走 TUS 分片上传。"""

        import tempfile
        with tempfile.NamedTemporaryFile(delete=True, suffix=".bin") as tmp:
            tmp.write(content)
            tmp.flush()
            return self._upload_file_tus(
                file_path=Path(tmp.name),
                object_path=object_path,
                content_type=content_type,
                upsert=upsert,
                bearer_token=bearer_token,
            )

    def _build_project_object_path(
        self,
        project_id: str,
        category: str,
        *parts: str,
    ) -> str:
        project_prefix = self.build_project_prefix(project_id)
        normalized_parts = [project_prefix, normalize_path_segment(category), *parts]
        return "/".join(
            normalize_path_segment(item)
            for item in normalized_parts
            if normalize_path_segment(item)
        )

    def _resolve_storage_bearer_token(self, bearer_token: str | None) -> str:
        return normalize_optional_str(bearer_token) or self.client.api_key

    @staticmethod
    def _quote_object_path(object_path: str) -> str:
        return parse.quote(object_path, safe="/")

    @staticmethod
    def _normalize_required_object_path(object_path: str) -> str:
        normalized_path = normalize_path_segment(object_path)
        if not normalized_path:
            raise SupabaseClientError("object_path 不能为空。")
        return normalized_path


def create_storage_service(
    *,
    secret_config_path: str | Path | None = None,
    params_config_path: str | Path | None = None,
    use_service_client: bool = True,
) -> SupabaseStorageService:
    """根据配置创建 Storage 服务。"""

    factory = SupabaseClientFactory(
        secret_config_path=secret_config_path,
        params_config_path=params_config_path,
    )
    client = factory.create_service_client() if use_service_client else factory.create_anon_client()
    storage_config = load_supabase_storage_config(params_config_path)
    return SupabaseStorageService(client=client, storage_config=storage_config)
