"""Sprout 媒体访问服务。"""

from __future__ import annotations

import mimetypes
import os
from dataclasses import dataclass
from typing import Any

from module.database.Supabase.storage import SupabaseStorageService, create_storage_service

from .cloud_asset_store import SproutCloudAssetStore


@dataclass
class SproutMediaService:
    """纯云端媒体服务，从 Supabase Storage 读取资产。"""

    cloud_asset_store: SproutCloudAssetStore | None = None
    storage_service: SupabaseStorageService | None = None

    def read_project_media(self, project_id: str, asset_path: str) -> tuple[str, bytes]:
        """从云端 Storage 下载资产字节流。"""

        row = self._find_asset_row(project_id, asset_path)
        if row is None:
            raise FileNotFoundError(f"云端未找到匹配的媒体资产：{asset_path}")

        object_path = row.get("object_path") or ""
        if not object_path:
            raise FileNotFoundError(f"资产记录缺少 object_path：{asset_path}")

        file_bytes = self._get_storage_service().download_object(object_path=object_path)
        mime_type, _ = mimetypes.guess_type(asset_path)
        return mime_type or "application/octet-stream", file_bytes

    def get_asset_signed_url(self, project_id: str, asset_path: str) -> str:
        """查找资产并返回签名 URL。"""

        row = self._find_asset_row(project_id, asset_path)
        if row is None:
            raise FileNotFoundError(f"云端未找到匹配的媒体资产：{asset_path}")

        object_path = row.get("object_path") or ""
        if not object_path:
            raise FileNotFoundError(f"资产记录缺少 object_path：{asset_path}")

        return self._get_storage_service().create_signed_url(object_path=object_path)

    def _find_asset_row(self, project_id: str, asset_path: str) -> dict[str, Any] | None:
        """在 project_assets 表中匹配资产。"""

        rows = self._get_cloud_asset_store().list_project_assets(project_id)
        if not rows:
            return None
        normalized_path = asset_path.strip().replace("\\", "/")
        file_name = os.path.basename(normalized_path)

        for row in rows:
            metadata = row.get("metadata") or {}
            local_path = str(metadata.get("local_path") or "").strip().replace("\\", "/")
            if local_path and (local_path == normalized_path or local_path.endswith(f"/{normalized_path}")):
                return row

        for row in rows:
            if row.get("asset_id") == normalized_path:
                return row

        for row in rows:
            row_object_path = str(row.get("object_path") or "")
            if row_object_path and os.path.basename(row_object_path) == file_name:
                return row

        return None

    def _get_cloud_asset_store(self) -> SproutCloudAssetStore:
        if self.cloud_asset_store is None:
            self.cloud_asset_store = SproutCloudAssetStore()
        return self.cloud_asset_store

    def _get_storage_service(self) -> SupabaseStorageService:
        if self.storage_service is None:
            self.storage_service = create_storage_service()
        return self.storage_service
