"""Sprout 资产云端存储映射。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from module.database.Supabase.project_tables import (
    SupabaseProjectTableService,
    SupabaseTableFilter,
    TABLE_PROJECT_ASSETS,
    create_project_table_service,
)
from module.database.Supabase.storage import (
    SupabaseStorageObjectRef,
    SupabaseStorageService,
    create_storage_service,
)

from ..core.models import SproutAsset


@dataclass
class SproutCloudAssetStore:
    """负责 `SproutAsset` 与云端资产表、Storage 的映射。"""

    table_service: SupabaseProjectTableService | None = None
    storage_service: SupabaseStorageService | None = None

    def upsert_asset_row(
        self,
        asset: SproutAsset,
        *,
        project_id: str,
        object_ref: SupabaseStorageObjectRef,
        shot_id: str | None = None,
        character_id: str | None = None,
        public_url: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """写入资产元数据。"""

        row = self.build_asset_row(
            asset,
            project_id=project_id,
            object_ref=object_ref,
            shot_id=shot_id,
            character_id=character_id,
            public_url=public_url,
            metadata=metadata,
        )
        response = self._get_table_service().upsert_rows(
            TABLE_PROJECT_ASSETS,
            row,
            on_conflict=("asset_id",),
        )
        return first_row_or_payload(response, default=row)

    def save_asset_file(
        self,
        asset: SproutAsset,
        *,
        project_id: str,
        file_path: str | Path,
        shot_id: str | None = None,
        character_id: str | None = None,
        content_type: str | None = None,
        metadata: dict[str, Any] | None = None,
        upsert: bool = True,
    ) -> dict[str, Any]:
        """上传本地资产并写入元数据。"""

        path = Path(file_path)
        object_path = self._get_storage_service().build_asset_object_path(
            project_id=project_id,
            asset_type=asset.asset_type,
            asset_id=asset.asset_id,
            file_name=path.name,
        )
        self._get_storage_service().upload_file(
            file_path=path,
            object_path=object_path,
            content_type=content_type,
            upsert=upsert,
        )
        return self.upsert_asset_row(
            asset,
            project_id=project_id,
            object_ref=SupabaseStorageObjectRef(
                bucket_name=self._get_storage_service().bucket_name,
                object_path=object_path,
            ),
            shot_id=shot_id,
            character_id=character_id,
            public_url=(
                self._get_storage_service().build_public_url(object_path)
                if self._get_storage_service().storage_config.public_bucket
                else None
            ),
            metadata=metadata,
        )

    def list_project_assets(self, project_id: str) -> list[dict[str, Any]]:
        """查询项目资产。"""

        response = self._get_table_service().select_rows(
            TABLE_PROJECT_ASSETS,
            filters=[SupabaseTableFilter("project_id", "eq", project_id)],
            order_by="created_at.asc",
        )
        return response if isinstance(response, list) else []

    def build_asset_row(
        self,
        asset: SproutAsset,
        *,
        project_id: str,
        object_ref: SupabaseStorageObjectRef,
        shot_id: str | None = None,
        character_id: str | None = None,
        public_url: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """将 `SproutAsset` 映射为数据库行。"""

        merged_metadata = dict(asset.metadata)
        if metadata:
            merged_metadata.update(metadata)
        if asset.path:
            merged_metadata.setdefault("local_path", asset.path)
        if asset.url:
            merged_metadata.setdefault("source_url", asset.url)

        owner_user_id = asset.owner_id
        if owner_user_id and not self._looks_like_uuid(owner_user_id):
            merged_metadata.setdefault("owner_name", owner_user_id)
            owner_user_id = None

        return {
            "asset_id": asset.asset_id,
            "project_id": project_id,
            "asset_type": asset.asset_type,
            "source": asset.source,
            "bucket_name": object_ref.bucket_name,
            "object_path": object_ref.object_path,
            "public_url": public_url,
            "role": asset.role,
            "prompt": asset.prompt,
            "owner_user_id": owner_user_id,
            "shot_id": shot_id,
            "character_id": character_id,
            "metadata": merged_metadata,
        }

    @staticmethod
    def _looks_like_uuid(value: str) -> bool:
        stripped = value.strip()
        return len(stripped) == 36 and stripped.count("-") == 4

    def _get_table_service(self) -> SupabaseProjectTableService:
        if self.table_service is None:
            self.table_service = create_project_table_service()
        return self.table_service

    def _get_storage_service(self) -> SupabaseStorageService:
        if self.storage_service is None:
            self.storage_service = create_storage_service()
        return self.storage_service


def first_row_or_payload(response: Any, *, default: dict[str, Any]) -> dict[str, Any]:
    """从 upsert/insert 返回中提取第一行。"""

    if isinstance(response, list) and response:
        first_row = response[0]
        if isinstance(first_row, dict):
            return first_row
    if isinstance(response, dict):
        return response
    return default
