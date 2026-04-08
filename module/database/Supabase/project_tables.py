"""Supabase 项目域表访问层。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .authorization import (
    PROJECT_ACTION_ASSET_DELETE,
    PROJECT_ACTION_ASSET_UPLOAD,
    PROJECT_ACTION_DELETE,
    PROJECT_ACTION_MEMBER_MANAGE,
    PROJECT_ACTION_READ,
    PROJECT_ACTION_RUN_RETRY,
    PROJECT_ACTION_UPDATE,
    PROJECT_ACTION_VERSION_ACTIVATE,
)
from .client import SupabaseClientFactory, SupabaseRestClient


TABLE_PROFILES = "profiles"
TABLE_PROJECTS = "projects"
TABLE_PROJECT_MEMBERS = "project_members"
TABLE_PROJECT_ASSETS = "project_assets"
TABLE_PROJECT_SNAPSHOTS = "project_snapshots"
TABLE_PROJECT_VERSIONS = "project_versions"
TABLE_PROJECT_RUNS = "project_runs"


@dataclass(frozen=True)
class SupabaseTableDefinition:
    """Supabase 表定义说明。"""

    table_name: str
    primary_keys: tuple[str, ...]
    project_scoped: bool
    description: str


@dataclass(frozen=True)
class SupabaseTableFilter:
    """PostgREST 过滤条件。"""

    column: str
    operator: str
    value: Any

    def to_query_pair(self) -> tuple[str, str]:
        return self.column, format_postgrest_filter(self.operator, self.value)


PHASE2_TABLE_DEFINITIONS = (
    SupabaseTableDefinition(
        table_name=TABLE_PROFILES,
        primary_keys=("id",),
        project_scoped=False,
        description="用户资料表，对齐 auth.users",
    ),
    SupabaseTableDefinition(
        table_name=TABLE_PROJECTS,
        primary_keys=("project_id",),
        project_scoped=True,
        description="项目主表，对齐项目注册信息",
    ),
    SupabaseTableDefinition(
        table_name=TABLE_PROJECT_MEMBERS,
        primary_keys=("project_id", "user_id"),
        project_scoped=True,
        description="项目成员关系表，承接 owner/editor/viewer",
    ),
    SupabaseTableDefinition(
        table_name=TABLE_PROJECT_ASSETS,
        primary_keys=("asset_id",),
        project_scoped=True,
        description="项目资产元数据表",
    ),
    SupabaseTableDefinition(
        table_name=TABLE_PROJECT_SNAPSHOTS,
        primary_keys=("snapshot_id",),
        project_scoped=True,
        description="项目快照元数据表",
    ),
    SupabaseTableDefinition(
        table_name=TABLE_PROJECT_VERSIONS,
        primary_keys=("version_id",),
        project_scoped=True,
        description="节点版本记录表",
    ),
    SupabaseTableDefinition(
        table_name=TABLE_PROJECT_RUNS,
        primary_keys=("run_id",),
        project_scoped=True,
        description="节点运行记录表",
    ),
)


PHASE2_ACTION_ROLE_GUIDE = {
    PROJECT_ACTION_READ: ("viewer", "editor", "owner"),
    PROJECT_ACTION_UPDATE: ("editor", "owner"),
    PROJECT_ACTION_DELETE: ("owner",),
    PROJECT_ACTION_MEMBER_MANAGE: ("owner",),
    PROJECT_ACTION_VERSION_ACTIVATE: ("owner",),
    PROJECT_ACTION_RUN_RETRY: ("editor", "owner"),
    PROJECT_ACTION_ASSET_UPLOAD: ("editor", "owner"),
    PROJECT_ACTION_ASSET_DELETE: ("owner",),
}


@dataclass
class SupabaseProjectTableService:
    """项目域表基础访问服务。"""

    client: SupabaseRestClient
    bearer_token: str | None = None

    def select_rows(
        self,
        table_name: str,
        *,
        columns: str = "*",
        filters: list[SupabaseTableFilter] | None = None,
        order_by: str | None = None,
        limit: int | None = None,
        single: bool = False,
    ) -> Any:
        query: dict[str, Any] = {"select": columns}
        for item in filters or []:
            key, value = item.to_query_pair()
            query[key] = value
        if order_by:
            query["order"] = order_by
        if limit is not None:
            query["limit"] = limit

        extra_headers = {"Accept": "application/vnd.pgrst.object+json"} if single else None
        return self.client.request_json(
            "GET",
            f"/{table_name}",
            base_path="rest",
            query=query,
            bearer_token=self.bearer_token,
            extra_headers=extra_headers,
        )

    def insert_rows(
        self,
        table_name: str,
        rows: list[dict[str, Any]] | dict[str, Any],
    ) -> Any:
        payload = rows if isinstance(rows, list) else [rows]
        response = self.client.request_json(
            "POST",
            f"/{table_name}",
            base_path="rest",
            body=payload,
            bearer_token=self.bearer_token,
            extra_headers={"Prefer": "return=representation"},
        )
        return response

    def upsert_rows(
        self,
        table_name: str,
        rows: list[dict[str, Any]] | dict[str, Any],
        *,
        on_conflict: tuple[str, ...] | None = None,
    ) -> Any:
        payload = rows if isinstance(rows, list) else [rows]
        query = {"on_conflict": ",".join(on_conflict)} if on_conflict else None
        return self.client.request_json(
            "POST",
            f"/{table_name}",
            base_path="rest",
            query=query,
            body=payload,
            bearer_token=self.bearer_token,
            extra_headers={"Prefer": "return=representation,resolution=merge-duplicates"},
        )

    def update_rows(
        self,
        table_name: str,
        *,
        values: dict[str, Any],
        filters: list[SupabaseTableFilter],
    ) -> Any:
        query = build_filter_query(filters)
        return self.client.request_json(
            "PATCH",
            f"/{table_name}",
            base_path="rest",
            query=query,
            body=values,
            bearer_token=self.bearer_token,
            extra_headers={"Prefer": "return=representation"},
        )

    def delete_rows(
        self,
        table_name: str,
        *,
        filters: list[SupabaseTableFilter],
    ) -> Any:
        query = build_filter_query(filters)
        return self.client.request_json(
            "DELETE",
            f"/{table_name}",
            base_path="rest",
            query=query,
            bearer_token=self.bearer_token,
            extra_headers={"Prefer": "return=representation"},
        )


def create_project_table_service(
    *,
    secret_config_path: str | Path | None = None,
    params_config_path: str | Path | None = None,
    use_service_client: bool = True,
) -> SupabaseProjectTableService:
    """根据配置创建项目域表服务。"""

    factory = SupabaseClientFactory(
        secret_config_path=secret_config_path,
        params_config_path=params_config_path,
    )
    client = factory.create_service_client() if use_service_client else factory.create_anon_client()
    return SupabaseProjectTableService(
        client=client,
        bearer_token=client.api_key if use_service_client else None,
    )


def build_filter_query(filters: list[SupabaseTableFilter]) -> dict[str, str]:
    """批量构造过滤参数。"""

    query: dict[str, str] = {}
    for item in filters:
        key, value = item.to_query_pair()
        query[key] = value
    return query


def format_postgrest_filter(operator: str, value: Any) -> str:
    """将过滤条件格式化为 PostgREST 语法。"""

    normalized_operator = str(operator or "").strip().lower() or "eq"
    if normalized_operator == "is" and value is None:
        return "is.null"
    if normalized_operator == "in":
        if not isinstance(value, (list, tuple, set)):
            raise ValueError("in 过滤条件的值必须是列表、元组或集合。")
        serialized_items = ",".join(serialize_filter_value(item) for item in value)
        return f"in.({serialized_items})"
    return f"{normalized_operator}.{serialize_filter_value(value)}"


def serialize_filter_value(value: Any) -> str:
    """序列化过滤值。"""

    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    text = str(value).strip()
    escaped = text.replace(",", r"\,")
    return escaped
