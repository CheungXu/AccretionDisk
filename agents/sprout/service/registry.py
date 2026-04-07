"""Sprout 项目注册表。"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from ..core.shared import ensure_directory, read_json_file, write_json_file
from .types import SproutImportedProjectRecord, utc_now_isoformat


@dataclass
class SproutProjectRegistry:
    """负责保存导入项目注册表。"""

    registry_root: str | Path | None = None

    def list_projects(self) -> list[SproutImportedProjectRecord]:
        payload = self._load_registry_payload()
        projects = [
            self._normalize_record_for_read(SproutImportedProjectRecord.from_dict(item))
            for item in payload.get("projects", [])
            if isinstance(item, dict)
        ]
        return sorted(projects, key=lambda item: item.last_active_at, reverse=True)

    def get_project(self, project_id: str) -> SproutImportedProjectRecord:
        normalized_id = project_id.strip()
        for record in self.list_projects():
            if record.project_id == normalized_id:
                return record
        raise KeyError(f"未找到项目：{project_id}")

    def upsert_project(self, record: SproutImportedProjectRecord) -> SproutImportedProjectRecord:
        projects = self.list_projects()
        replaced = False
        for index, existing in enumerate(projects):
            if existing.project_id == record.project_id:
                projects[index] = record
                replaced = True
                break
        if not replaced:
            projects.append(record)
        self._save_projects(projects)
        return record

    def touch_project(self, project_id: str) -> SproutImportedProjectRecord:
        record = self.get_project(project_id)
        record.last_active_at = utc_now_isoformat()
        return self.upsert_project(record)

    def _save_projects(self, projects: list[SproutImportedProjectRecord]) -> Path:
        registry_path = self._get_registry_path()
        serializable = [
            self._relativize_record_for_write(record).to_dict() for record in projects
        ]
        return write_json_file(registry_path, {"projects": serializable})

    def _load_registry_payload(self) -> dict[str, object]:
        registry_path = self._get_registry_path()
        if not registry_path.exists():
            return {"projects": []}
        payload = read_json_file(registry_path)
        return payload if isinstance(payload, dict) else {"projects": []}

    def _get_registry_path(self) -> Path:
        registry_root = ensure_directory(self._resolve_registry_root())
        return registry_root / "projects.json"

    def _resolve_registry_root(self) -> Path:
        if self.registry_root is not None:
            return Path(self.registry_root).expanduser()
        repo_root = Path(__file__).resolve().parents[3]
        return repo_root / "data" / "sprout" / "project_registry"

    def _default_repo_root(self) -> Path:
        return Path(__file__).resolve().parents[3]

    def _anchor_for_relative_paths(self) -> Path | None:
        """使用默认注册表目录时，相对路径按仓库根解析/回写。"""
        return self._default_repo_root() if self.registry_root is None else None

    def _normalize_path_for_read(self, value: str | None) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return value
        path = Path(text)
        if path.is_absolute():
            return str(path.expanduser().resolve())
        anchor = self._anchor_for_relative_paths()
        if anchor is None:
            return str(path.resolve())
        return str((anchor / path).resolve())

    def _normalize_record_for_read(self, record: SproutImportedProjectRecord) -> SproutImportedProjectRecord:
        return replace(
            record,
            project_root=self._normalize_path_for_read(record.project_root) or "",
            canonical_root=self._normalize_path_for_read(record.canonical_root) or "",
            bundle_path=self._normalize_path_for_read(record.bundle_path) or "",
            manifest_path=self._normalize_path_for_read(record.manifest_path),
            cover_asset_path=self._normalize_path_for_read(record.cover_asset_path),
        )

    def _relativize_path_for_write(self, value: str | None, anchor: Path) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return value
        path = Path(text)
        if not path.is_absolute():
            return path.as_posix()
        resolved = path.expanduser().resolve()
        anchor_resolved = anchor.resolve()
        try:
            return resolved.relative_to(anchor_resolved).as_posix()
        except ValueError:
            return str(resolved)

    def _relativize_record_for_write(self, record: SproutImportedProjectRecord) -> SproutImportedProjectRecord:
        anchor = self._anchor_for_relative_paths()
        if anchor is None:
            return record
        return replace(
            record,
            project_root=self._relativize_path_for_write(record.project_root, anchor) or "",
            canonical_root=self._relativize_path_for_write(record.canonical_root, anchor) or "",
            bundle_path=self._relativize_path_for_write(record.bundle_path, anchor) or "",
            manifest_path=self._relativize_path_for_write(record.manifest_path, anchor),
            cover_asset_path=self._relativize_path_for_write(record.cover_asset_path, anchor),
        )
