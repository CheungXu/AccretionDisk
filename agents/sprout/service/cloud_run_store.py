"""Sprout 运行记录云端映射。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from module.database.Supabase.project_tables import (
    SupabaseProjectTableService,
    SupabaseTableFilter,
    TABLE_PROJECT_RUNS,
    create_project_table_service,
)
from module.database.Supabase.storage import (
    SupabaseStorageObjectRef,
    SupabaseStorageService,
    create_storage_service,
)

from .types import SproutRunRecord


@dataclass
class SproutCloudRunStore:
    """负责 `SproutRunRecord` 与运行日志的云端映射。"""

    table_service: SupabaseProjectTableService | None = None
    storage_service: SupabaseStorageService | None = None

    def upsert_run_record(
        self,
        run_record: SproutRunRecord,
        *,
        log_object_ref: SupabaseStorageObjectRef | None = None,
    ) -> dict[str, Any]:
        """写入运行记录。"""

        row = self.build_run_row(run_record, log_object_ref=log_object_ref)
        response = self._get_table_service().upsert_rows(
            TABLE_PROJECT_RUNS,
            row,
            on_conflict=("run_id",),
        )
        return first_row_or_payload(response, default=row)

    def save_run_log(
        self,
        *,
        project_id: str,
        run_record: SproutRunRecord,
        log_text: str,
    ) -> dict[str, Any]:
        """上传运行日志并更新运行记录。"""

        object_path = self._get_storage_service().build_log_object_path(
            project_id=project_id,
            run_id=run_record.run_id,
        )
        self._get_storage_service().upload_text(
            object_path=object_path,
            content=log_text,
            content_type="text/plain; charset=utf-8",
            upsert=True,
        )
        return self.upsert_run_record(
            run_record,
            log_object_ref=SupabaseStorageObjectRef(
                bucket_name=self._get_storage_service().bucket_name,
                object_path=object_path,
            ),
        )

    def list_project_runs(
        self,
        project_id: str,
        *,
        node_type: str | None = None,
        node_key: str | None = None,
    ) -> list[dict[str, Any]]:
        """查询项目运行记录。"""

        filters = [SupabaseTableFilter("project_id", "eq", project_id)]
        if node_type:
            filters.append(SupabaseTableFilter("node_type", "eq", node_type))
        if node_key:
            filters.append(SupabaseTableFilter("node_key", "eq", node_key))
        response = self._get_table_service().select_rows(
            TABLE_PROJECT_RUNS,
            filters=filters,
            order_by="created_at.desc",
        )
        return response if isinstance(response, list) else []

    def build_run_row(
        self,
        run_record: SproutRunRecord,
        *,
        log_object_ref: SupabaseStorageObjectRef | None = None,
    ) -> dict[str, Any]:
        """将运行记录映射为数据库行。"""

        return {
            "run_id": run_record.run_id,
            "project_id": run_record.project_id,
            "node_type": run_record.node_type,
            "node_key": run_record.node_key,
            "log_bucket_name": log_object_ref.bucket_name if log_object_ref else None,
            "log_object_path": log_object_ref.object_path if log_object_ref else run_record.log_path,
            "status": run_record.status,
            "source_version_id": run_record.source_version_id,
            "result_version_id": run_record.result_version_id,
            "shot_ids": list(run_record.shot_ids),
            "error_message": run_record.error_message,
            "created_at": run_record.created_at,
            "updated_at": run_record.updated_at,
        }

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
