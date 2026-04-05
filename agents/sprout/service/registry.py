"""Sprout 项目注册表。"""

from __future__ import annotations

from dataclasses import dataclass
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
            SproutImportedProjectRecord.from_dict(item)
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
        return write_json_file(
            registry_path,
            {"projects": [record.to_dict() for record in projects]},
        )

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
