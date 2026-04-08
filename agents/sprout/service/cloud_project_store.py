"""Sprout 项目云端存储映射。"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from module.database.Supabase.authorization import normalize_project_role
from module.database.Supabase.project_tables import (
    SupabaseProjectTableService,
    SupabaseTableFilter,
    TABLE_PROJECTS,
    TABLE_PROJECT_MEMBERS,
    TABLE_PROJECT_SNAPSHOTS,
    create_project_table_service,
)
from module.database.Supabase.storage import (
    SupabaseStorageObjectRef,
    SupabaseStorageService,
    create_storage_service,
)

from ..core.models import SproutProjectBundle
from .types import SproutImportedProjectRecord, build_runtime_id, utc_now_isoformat


@dataclass
class SproutCloudProjectStore:
    """负责 `sprout` 项目到云端项目表与快照表的映射。"""

    table_service: SupabaseProjectTableService | None = None
    storage_service: SupabaseStorageService | None = None

    def upsert_project_record(
        self,
        record: SproutImportedProjectRecord,
        *,
        bundle: SproutProjectBundle | None = None,
        created_by: str | None = None,
        cover_asset_id: str | None = None,
        current_manifest_snapshot_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """将本地项目注册记录写入云端项目表。"""

        row = self.build_project_row(
            record,
            bundle=bundle,
            created_by=created_by,
            cover_asset_id=cover_asset_id,
            current_manifest_snapshot_id=current_manifest_snapshot_id,
            metadata=metadata,
        )
        response = self._get_table_service().upsert_rows(
            TABLE_PROJECTS,
            row,
            on_conflict=("project_id",),
        )
        return first_row_or_payload(response, default=row)

    def add_project_member(
        self,
        *,
        project_id: str,
        user_id: str,
        role: str,
        invited_by: str | None = None,
        status: str = "active",
    ) -> dict[str, Any]:
        """新增或更新项目成员。"""

        row = self.build_project_member_row(
            project_id=project_id,
            user_id=user_id,
            role=role,
            invited_by=invited_by,
            status=status,
        )
        response = self._get_table_service().upsert_rows(
            TABLE_PROJECT_MEMBERS,
            row,
            on_conflict=("project_id", "user_id"),
        )
        return first_row_or_payload(response, default=row)

    def list_project_members(self, project_id: str) -> list[dict[str, Any]]:
        """查询项目成员。"""

        response = self._get_table_service().select_rows(
            TABLE_PROJECT_MEMBERS,
            filters=[SupabaseTableFilter("project_id", "eq", project_id)],
            order_by="joined_at.asc",
        )
        return response if isinstance(response, list) else []

    def get_project_member(self, *, project_id: str, user_id: str) -> dict[str, Any] | None:
        """读取单个项目成员。"""

        response = self._get_table_service().select_rows(
            TABLE_PROJECT_MEMBERS,
            filters=[
                SupabaseTableFilter("project_id", "eq", project_id),
                SupabaseTableFilter("user_id", "eq", user_id),
            ],
            single=True,
        )
        return response if isinstance(response, dict) else None

    def list_projects_for_user(self, user_id: str) -> list[dict[str, Any]]:
        """列出某个用户可访问的项目。"""

        memberships = self._get_table_service().select_rows(
            TABLE_PROJECT_MEMBERS,
            filters=[
                SupabaseTableFilter("user_id", "eq", user_id),
                SupabaseTableFilter("status", "eq", "active"),
            ],
            order_by="joined_at.asc",
        )
        if not isinstance(memberships, list) or not memberships:
            return []

        project_ids = [
            str(item.get("project_id")).strip()
            for item in memberships
            if isinstance(item, dict) and str(item.get("project_id") or "").strip()
        ]
        if not project_ids:
            return []

        projects = self._get_table_service().select_rows(
            TABLE_PROJECTS,
            filters=[SupabaseTableFilter("project_id", "in", project_ids)],
            order_by="last_active_at.desc",
        )
        if not isinstance(projects, list):
            return []

        role_by_project_id = {
            str(item.get("project_id")).strip(): str(item.get("role") or "").strip()
            for item in memberships
            if isinstance(item, dict)
        }
        for project in projects:
            if not isinstance(project, dict):
                continue
            project["current_user_role"] = role_by_project_id.get(str(project.get("project_id") or "").strip())
        return projects

    def get_project_row(self, project_id: str) -> dict[str, Any] | None:
        """读取单个项目。"""

        response = self._get_table_service().select_rows(
            TABLE_PROJECTS,
            filters=[SupabaseTableFilter("project_id", "eq", project_id)],
            single=True,
        )
        return response if isinstance(response, dict) else None

    def build_record_from_project_row(self, project_row: dict[str, Any]) -> SproutImportedProjectRecord:
        """将云端项目行还原为本地路径记录。"""

        metadata = project_row.get("metadata")
        metadata_dict = metadata if isinstance(metadata, dict) else {}
        local_paths = metadata_dict.get("local_paths")
        local_paths_dict = local_paths if isinstance(local_paths, dict) else {}
        notes = metadata_dict.get("notes")
        if not isinstance(notes, list):
            notes = []
        return SproutImportedProjectRecord(
            project_id=str(project_row.get("project_id") or "").strip(),
            project_type=str(project_row.get("project_type") or "sprout").strip(),
            display_name=str(project_row.get("display_name") or "").strip(),
            project_name=str(project_row.get("project_name") or "").strip(),
            project_root=str(local_paths_dict.get("project_root") or "").strip(),
            canonical_root=str(local_paths_dict.get("canonical_root") or "").strip(),
            bundle_path=str(local_paths_dict.get("bundle_path") or "").strip(),
            manifest_path=str(local_paths_dict.get("manifest_path") or "").strip() or None,
            cover_asset_path=str(local_paths_dict.get("cover_asset_path") or "").strip() or None,
            import_mode=str(project_row.get("import_mode") or "reference").strip(),
            schema_version=str(project_row.get("schema_version") or "v1").strip(),
            health_status=str(project_row.get("health_status") or "ready").strip(),
            imported_at=str(project_row.get("imported_at") or utc_now_isoformat()).strip(),
            last_active_at=str(project_row.get("last_active_at") or utc_now_isoformat()).strip(),
            notes=[str(item).strip() for item in notes if str(item).strip()],
        )

    def save_bundle_snapshot(
        self,
        *,
        project_id: str,
        project_bundle: SproutProjectBundle,
        created_by: str | None = None,
        snapshot_id: str | None = None,
        snapshot_type: str = "bundle",
        source_version_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """保存项目 bundle 快照。"""

        return self.save_snapshot_payload(
            project_id=project_id,
            snapshot_payload=project_bundle.to_dict(),
            created_by=created_by,
            snapshot_id=snapshot_id,
            snapshot_type=snapshot_type,
            source_version_id=source_version_id,
            metadata=metadata,
        )

    def save_snapshot_payload(
        self,
        *,
        project_id: str,
        snapshot_payload: dict[str, Any],
        created_by: str | None = None,
        snapshot_id: str | None = None,
        snapshot_type: str,
        source_version_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """保存任意 JSON 快照到 Storage，并写入快照元数据。"""

        final_snapshot_id = snapshot_id or build_runtime_id(f"snapshot_{snapshot_type}")
        content_text = json.dumps(snapshot_payload, ensure_ascii=False, indent=2)
        content_sha256 = hashlib.sha256(content_text.encode("utf-8")).hexdigest()
        object_path = self._get_storage_service().build_snapshot_object_path(
            project_id=project_id,
            snapshot_type=snapshot_type,
            file_name=f"{final_snapshot_id}.json",
        )
        self._get_storage_service().upload_text(
            object_path=object_path,
            content=content_text,
            content_type="application/json; charset=utf-8",
            upsert=True,
        )

        row = self.build_snapshot_row(
            snapshot_id=final_snapshot_id,
            project_id=project_id,
            snapshot_type=snapshot_type,
            object_ref=SupabaseStorageObjectRef(
                bucket_name=self._get_storage_service().bucket_name,
                object_path=object_path,
            ),
            content_sha256=content_sha256,
            source_version_id=source_version_id,
            created_by=created_by,
            metadata=metadata,
        )
        response = self._get_table_service().upsert_rows(
            TABLE_PROJECT_SNAPSHOTS,
            row,
            on_conflict=("snapshot_id",),
        )
        return first_row_or_payload(response, default=row)

    def build_project_row(
        self,
        record: SproutImportedProjectRecord,
        *,
        bundle: SproutProjectBundle | None = None,
        created_by: str | None = None,
        cover_asset_id: str | None = None,
        current_manifest_snapshot_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """将本地项目注册记录映射为数据库行。"""

        manifest_status = bundle.manifest.status if bundle and bundle.manifest else None
        merged_metadata: dict[str, Any] = {
            "local_paths": {
                "project_root": record.project_root,
                "canonical_root": record.canonical_root,
                "bundle_path": record.bundle_path,
                "manifest_path": record.manifest_path,
                "cover_asset_path": record.cover_asset_path,
            },
            "notes": list(record.notes),
        }
        if metadata:
            merged_metadata.update(metadata)

        return {
            "project_id": record.project_id,
            "project_type": record.project_type,
            "display_name": record.display_name,
            "project_name": record.project_name,
            "title": bundle.episode.title if bundle else None,
            "topic": bundle.topic_input.topic if bundle else None,
            "status": manifest_status or "draft",
            "schema_version": record.schema_version,
            "import_mode": record.import_mode,
            "health_status": record.health_status,
            "cover_asset_id": cover_asset_id,
            "current_manifest_snapshot_id": current_manifest_snapshot_id,
            "created_by": created_by,
            "imported_at": record.imported_at,
            "last_active_at": record.last_active_at,
            "metadata": merged_metadata,
        }

    def build_project_member_row(
        self,
        *,
        project_id: str,
        user_id: str,
        role: str,
        invited_by: str | None = None,
        status: str = "active",
    ) -> dict[str, Any]:
        """构造项目成员行。"""

        return {
            "project_id": project_id,
            "user_id": user_id,
            "role": normalize_project_role(role),
            "invited_by": invited_by,
            "status": status,
            "joined_at": utc_now_isoformat(),
            "updated_at": utc_now_isoformat(),
        }

    def build_snapshot_row(
        self,
        *,
        snapshot_id: str,
        project_id: str,
        snapshot_type: str,
        object_ref: SupabaseStorageObjectRef,
        content_sha256: str | None = None,
        source_version_id: str | None = None,
        created_by: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """构造快照元数据行。"""

        return {
            "snapshot_id": snapshot_id,
            "project_id": project_id,
            "snapshot_type": snapshot_type,
            "bucket_name": object_ref.bucket_name,
            "object_path": object_ref.object_path,
            "content_sha256": content_sha256,
            "source_version_id": source_version_id,
            "created_by": created_by,
            "created_at": utc_now_isoformat(),
            "metadata": metadata or {},
        }

    def get_active_state(self, project_id: str) -> dict[str, Any]:
        """从 projects 表读取版本激活状态。"""

        project_row = self.get_project_row(project_id)
        if not isinstance(project_row, dict):
            return {
                "active_bundle_version_id": None,
                "active_bundle_snapshot_id": None,
                "selected_versions": {},
                "updated_at": None,
            }
        active_state = project_row.get("active_state")
        return active_state if isinstance(active_state, dict) else {}

    def update_active_state(self, project_id: str, active_state: dict[str, Any]) -> dict[str, Any]:
        """更新 projects 表的版本激活状态。"""

        active_state["updated_at"] = utc_now_isoformat()
        response = self._get_table_service().update_rows(
            TABLE_PROJECTS,
            values={"active_state": active_state, "last_active_at": utc_now_isoformat()},
            filters=[SupabaseTableFilter("project_id", "eq", project_id)],
        )
        return active_state

    def download_snapshot(self, snapshot_id: str, project_id: str) -> dict[str, Any]:
        """从 Storage 下载快照 JSON 并返回反序列化后的内容。"""

        snapshot_rows = self._get_table_service().select_rows(
            TABLE_PROJECT_SNAPSHOTS,
            filters=[
                SupabaseTableFilter("snapshot_id", "eq", snapshot_id),
                SupabaseTableFilter("project_id", "eq", project_id),
            ],
            single=True,
        )
        if not isinstance(snapshot_rows, dict):
            raise KeyError(f"未找到快照：{snapshot_id}")
        object_path = str(snapshot_rows.get("object_path") or "").strip()
        if not object_path:
            raise ValueError(f"快照缺少 object_path：{snapshot_id}")
        raw_bytes = self._get_storage_service().download_object(object_path=object_path)
        return json.loads(raw_bytes.decode("utf-8"))

    def download_latest_bundle_snapshot(self, project_id: str) -> dict[str, Any] | None:
        """下载项目最新的 bundle 快照。优先使用 current_manifest_snapshot_id 对应的 bundle。"""

        project_row = self.get_project_row(project_id)
        if not isinstance(project_row, dict):
            return None
        snapshot_rows = self._get_table_service().select_rows(
            TABLE_PROJECT_SNAPSHOTS,
            filters=[
                SupabaseTableFilter("project_id", "eq", project_id),
                SupabaseTableFilter("snapshot_type", "eq", "bundle"),
            ],
            order_by="created_at.desc",
            limit=1,
        )
        if not isinstance(snapshot_rows, list) or not snapshot_rows:
            return None
        row = snapshot_rows[0]
        object_path = str(row.get("object_path") or "").strip()
        if not object_path:
            return None
        raw_bytes = self._get_storage_service().download_object(object_path=object_path)
        return json.loads(raw_bytes.decode("utf-8"))

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
