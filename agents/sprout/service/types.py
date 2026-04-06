"""Sprout 后端服务层数据结构。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now_isoformat() -> str:
    """返回 UTC ISO 时间字符串。"""

    return datetime.now(timezone.utc).isoformat()


def build_runtime_id(prefix: str) -> str:
    """生成运行时稳定 ID。"""

    timestamp_text = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    return f"{prefix}_{timestamp_text}"


def _coerce_string(value: Any) -> str | None:
    if value is None:
        return None
    normalized_value = str(value).strip()
    return normalized_value or None


def _coerce_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    normalized_value = str(value).strip()
    return [normalized_value] if normalized_value else []


def _coerce_string_dict(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    normalized_dict: dict[str, str] = {}
    for key, item in value.items():
        normalized_key = str(key).strip()
        normalized_value = str(item).strip()
        if normalized_key and normalized_value:
            normalized_dict[normalized_key] = normalized_value
    return normalized_dict


@dataclass
class SproutImportedProjectRecord:
    """导入项目注册信息。"""

    project_id: str
    project_type: str
    display_name: str
    project_name: str
    project_root: str
    canonical_root: str
    bundle_path: str
    manifest_path: str | None = None
    cover_asset_path: str | None = None
    import_mode: str = "reference"
    schema_version: str = "v1"
    health_status: str = "ready"
    imported_at: str = field(default_factory=utc_now_isoformat)
    last_active_at: str = field(default_factory=utc_now_isoformat)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "project_type": self.project_type,
            "display_name": self.display_name,
            "project_name": self.project_name,
            "project_root": self.project_root,
            "canonical_root": self.canonical_root,
            "bundle_path": self.bundle_path,
            "manifest_path": self.manifest_path,
            "cover_asset_path": self.cover_asset_path,
            "import_mode": self.import_mode,
            "schema_version": self.schema_version,
            "health_status": self.health_status,
            "imported_at": self.imported_at,
            "last_active_at": self.last_active_at,
            "notes": list(self.notes),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SproutImportedProjectRecord":
        return cls(
            project_id=str(payload.get("project_id") or "").strip(),
            project_type=str(payload.get("project_type") or "sprout").strip(),
            display_name=str(payload.get("display_name") or "").strip(),
            project_name=str(payload.get("project_name") or "").strip(),
            project_root=str(payload.get("project_root") or "").strip(),
            canonical_root=str(payload.get("canonical_root") or "").strip(),
            bundle_path=str(payload.get("bundle_path") or "").strip(),
            manifest_path=_coerce_string(payload.get("manifest_path")),
            cover_asset_path=_coerce_string(payload.get("cover_asset_path")),
            import_mode=str(payload.get("import_mode") or "reference").strip(),
            schema_version=str(payload.get("schema_version") or "v1").strip(),
            health_status=str(payload.get("health_status") or "ready").strip(),
            imported_at=str(payload.get("imported_at") or utc_now_isoformat()).strip(),
            last_active_at=str(payload.get("last_active_at") or utc_now_isoformat()).strip(),
            notes=_coerce_list(payload.get("notes")),
        )


@dataclass
class SproutNodeVersionRecord:
    """节点版本快照记录。"""

    version_id: str
    project_id: str
    node_type: str
    node_key: str
    bundle_snapshot_path: str
    source_version_id: str | None = None
    status: str = "ready"
    created_at: str = field(default_factory=utc_now_isoformat)
    run_id: str | None = None
    asset_ids: list[str] = field(default_factory=list)
    shot_ids: list[str] = field(default_factory=list)
    dependency_version_ids: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version_id": self.version_id,
            "project_id": self.project_id,
            "node_type": self.node_type,
            "node_key": self.node_key,
            "bundle_snapshot_path": self.bundle_snapshot_path,
            "source_version_id": self.source_version_id,
            "status": self.status,
            "created_at": self.created_at,
            "run_id": self.run_id,
            "asset_ids": list(self.asset_ids),
            "shot_ids": list(self.shot_ids),
            "dependency_version_ids": dict(self.dependency_version_ids),
            "notes": list(self.notes),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SproutNodeVersionRecord":
        return cls(
            version_id=str(payload.get("version_id") or "").strip(),
            project_id=str(payload.get("project_id") or "").strip(),
            node_type=str(payload.get("node_type") or "").strip(),
            node_key=str(payload.get("node_key") or "").strip(),
            bundle_snapshot_path=str(payload.get("bundle_snapshot_path") or "").strip(),
            source_version_id=_coerce_string(payload.get("source_version_id")),
            status=str(payload.get("status") or "ready").strip(),
            created_at=str(payload.get("created_at") or utc_now_isoformat()).strip(),
            run_id=_coerce_string(payload.get("run_id")),
            asset_ids=_coerce_list(payload.get("asset_ids")),
            shot_ids=_coerce_list(payload.get("shot_ids")),
            dependency_version_ids=_coerce_string_dict(payload.get("dependency_version_ids")),
            notes=_coerce_list(payload.get("notes")),
        )


@dataclass
class SproutRunRecord:
    """节点执行记录。"""

    run_id: str
    project_id: str
    node_type: str
    node_key: str
    log_path: str
    status: str = "running"
    created_at: str = field(default_factory=utc_now_isoformat)
    updated_at: str = field(default_factory=utc_now_isoformat)
    source_version_id: str | None = None
    result_version_id: str | None = None
    shot_ids: list[str] = field(default_factory=list)
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "project_id": self.project_id,
            "node_type": self.node_type,
            "node_key": self.node_key,
            "log_path": self.log_path,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "source_version_id": self.source_version_id,
            "result_version_id": self.result_version_id,
            "shot_ids": list(self.shot_ids),
            "error_message": self.error_message,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SproutRunRecord":
        return cls(
            run_id=str(payload.get("run_id") or "").strip(),
            project_id=str(payload.get("project_id") or "").strip(),
            node_type=str(payload.get("node_type") or "").strip(),
            node_key=str(payload.get("node_key") or "").strip(),
            log_path=str(payload.get("log_path") or "").strip(),
            status=str(payload.get("status") or "running").strip(),
            created_at=str(payload.get("created_at") or utc_now_isoformat()).strip(),
            updated_at=str(payload.get("updated_at") or utc_now_isoformat()).strip(),
            source_version_id=_coerce_string(payload.get("source_version_id")),
            result_version_id=_coerce_string(payload.get("result_version_id")),
            shot_ids=_coerce_list(payload.get("shot_ids")),
            error_message=_coerce_string(payload.get("error_message")),
        )
