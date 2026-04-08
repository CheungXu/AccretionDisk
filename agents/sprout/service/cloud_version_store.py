"""Sprout 版本云端存储映射。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from module.database.Supabase.project_tables import (
    SupabaseProjectTableService,
    SupabaseTableFilter,
    TABLE_PROJECT_VERSIONS,
    create_project_table_service,
)

from .types import SproutNodeVersionRecord, build_runtime_id, utc_now_isoformat


@dataclass
class SproutCloudVersionStore:
    """负责 `SproutNodeVersionRecord` 到云端版本表的映射。"""

    table_service: SupabaseProjectTableService | None = None

    def upsert_version_record(
        self,
        version_record: SproutNodeVersionRecord,
        *,
        snapshot_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """写入节点版本记录。"""

        row = self.build_version_row(
            version_record,
            snapshot_id=snapshot_id,
            metadata=metadata,
        )
        response = self._get_table_service().upsert_rows(
            TABLE_PROJECT_VERSIONS,
            row,
            on_conflict=("version_id",),
        )
        return first_row_or_payload(response, default=row)

    def list_project_versions(
        self,
        project_id: str,
        *,
        node_type: str | None = None,
        node_key: str | None = None,
    ) -> list[dict[str, Any]]:
        """查询项目版本记录。"""

        filters = [SupabaseTableFilter("project_id", "eq", project_id)]
        if node_type:
            filters.append(SupabaseTableFilter("node_type", "eq", node_type))
        if node_key:
            filters.append(SupabaseTableFilter("node_key", "eq", node_key))

        response = self._get_table_service().select_rows(
            TABLE_PROJECT_VERSIONS,
            filters=filters,
            order_by="created_at.desc",
        )
        return response if isinstance(response, list) else []

    def build_version_row(
        self,
        version_record: SproutNodeVersionRecord,
        *,
        snapshot_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """将版本记录映射为数据库行。"""

        notes = list(version_record.notes)
        if metadata:
            notes.extend([f"metadata:{key}" for key in sorted(metadata.keys())])

        return {
            "version_id": version_record.version_id,
            "project_id": version_record.project_id,
            "node_type": version_record.node_type,
            "node_key": version_record.node_key,
            "snapshot_id": snapshot_id,
            "source_version_id": version_record.source_version_id,
            "status": version_record.status,
            "run_id": version_record.run_id,
            "asset_ids": list(version_record.asset_ids),
            "shot_ids": list(version_record.shot_ids),
            "dependency_version_ids": dict(version_record.dependency_version_ids),
            "notes": notes,
            "created_at": version_record.created_at,
        }

    def get_version_row(self, version_id: str) -> dict[str, Any] | None:
        """读取单个版本记录。"""

        response = self._get_table_service().select_rows(
            TABLE_PROJECT_VERSIONS,
            filters=[SupabaseTableFilter("version_id", "eq", version_id)],
            single=True,
        )
        return response if isinstance(response, dict) else None

    def build_version_record_from_row(self, row: dict[str, Any]) -> SproutNodeVersionRecord:
        """将数据库行还原为 SproutNodeVersionRecord。"""

        dependency_version_ids = row.get("dependency_version_ids")
        if not isinstance(dependency_version_ids, dict):
            dependency_version_ids = {}
        asset_ids = row.get("asset_ids")
        if not isinstance(asset_ids, list):
            asset_ids = []
        shot_ids = row.get("shot_ids")
        if not isinstance(shot_ids, list):
            shot_ids = []
        notes = row.get("notes")
        if not isinstance(notes, list):
            notes = []
        return SproutNodeVersionRecord(
            version_id=str(row.get("version_id") or "").strip(),
            project_id=str(row.get("project_id") or "").strip(),
            node_type=str(row.get("node_type") or "").strip(),
            node_key=str(row.get("node_key") or "").strip(),
            bundle_snapshot_path="",
            source_version_id=row.get("source_version_id"),
            run_id=row.get("run_id"),
            status=str(row.get("status") or "ready").strip(),
            asset_ids=[str(item) for item in asset_ids],
            shot_ids=[str(item) for item in shot_ids],
            dependency_version_ids={str(k): str(v) for k, v in dependency_version_ids.items()},
            notes=[str(item) for item in notes],
            created_at=str(row.get("created_at") or utc_now_isoformat()).strip(),
        )

    def _get_table_service(self) -> SupabaseProjectTableService:
        if self.table_service is None:
            self.table_service = create_project_table_service()
        return self.table_service


def first_row_or_payload(response: Any, *, default: dict[str, Any]) -> dict[str, Any]:
    """从 upsert/insert 返回中提取第一行。"""

    if isinstance(response, list) and response:
        first_row = response[0]
        if isinstance(first_row, dict):
            return first_row
    if isinstance(response, dict):
        return response
    return default
