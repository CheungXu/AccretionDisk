"""Sprout 项目查询与导入服务。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..core.shared import read_json_file
from ..core.storage import SproutProjectStore
from .adapters import SproutProjectAdapter
from .registry import SproutProjectRegistry
from .runtime import SproutRunStore, SproutVersionStore
from .types import SproutImportedProjectRecord


@dataclass
class SproutProjectService:
    """负责项目导入、查询与激活版本切换。"""

    adapter: SproutProjectAdapter | None = None
    registry: SproutProjectRegistry | None = None
    version_store: SproutVersionStore | None = None
    run_store: SproutRunStore | None = None
    project_store: SproutProjectStore | None = None

    def import_project(
        self,
        project_root: str | Path,
        *,
        import_mode: str = "reference",
    ) -> dict[str, Any]:
        record = self._get_adapter().import_project(project_root, import_mode=import_mode)
        saved_record = self._get_registry().upsert_project(record)
        return self._build_project_summary(saved_record)

    def list_projects(self) -> list[dict[str, Any]]:
        return [self._build_project_summary(record) for record in self._get_registry().list_projects()]

    def get_project_detail(self, project_id: str) -> dict[str, Any]:
        record = self._get_registry().get_project(project_id)
        bundle = self._get_project_store().load_bundle(record.bundle_path)
        manifest_payload = (
            read_json_file(record.manifest_path)
            if record.manifest_path and Path(record.manifest_path).exists()
            else bundle.ensure_manifest(output_root=str(Path(record.canonical_root))).to_dict()
        )
        versions = self._get_version_store().list_versions(record.canonical_root)
        active_state = self._get_version_store().get_active_state(record.canonical_root)
        return {
            "project": self._build_project_summary(record),
            "bundle": bundle.to_dict(),
            "manifest": manifest_payload if isinstance(manifest_payload, dict) else {},
            "nodes": self._build_node_summaries(bundle, versions),
            "versions": [version.to_dict() for version in versions],
            "active_state": active_state,
        }

    def list_versions(
        self,
        project_id: str,
        *,
        node_type: str | None = None,
        node_key: str | None = None,
    ) -> list[dict[str, Any]]:
        record = self._get_registry().get_project(project_id)
        versions = self._get_version_store().list_versions(
            record.canonical_root,
            node_type=node_type,
            node_key=node_key,
        )
        return [version.to_dict() for version in versions]

    def get_version_detail(self, project_id: str, version_id: str) -> dict[str, Any]:
        record = self._get_registry().get_project(project_id)
        return self._get_version_store().get_version_detail(record.canonical_root, version_id)

    def get_node_detail(
        self,
        project_id: str,
        *,
        node_type: str,
        node_key: str,
    ) -> dict[str, Any]:
        record = self._get_registry().get_project(project_id)
        bundle = self._get_project_store().load_bundle(record.bundle_path)
        versions = self._get_version_store().list_versions(
            record.canonical_root,
            node_type=node_type,
            node_key=node_key,
        )
        runs = self._get_run_store().list_runs(
            record.canonical_root,
            node_type=node_type,
            node_key=node_key,
        )
        active_state = self._get_version_store().get_active_state(record.canonical_root)
        active_version_id = None
        selected_versions = active_state.get("selected_versions", {})
        if isinstance(selected_versions, dict):
            active_version_id = selected_versions.get(f"{node_type}:{node_key}")

        return {
            "project": self._build_project_summary(record),
            "node": self._build_node_detail_payload(
                bundle=bundle,
                node_type=node_type,
                node_key=node_key,
                active_version_id=active_version_id,
            ),
            "versions": [version.to_dict() for version in versions],
            "runs": [run.to_dict() for run in runs],
            "active_state": active_state,
        }

    def activate_version(self, project_id: str, version_id: str) -> dict[str, Any]:
        record = self._get_registry().get_project(project_id)
        active_state = self._get_version_store().activate_version(
            project_root=record.canonical_root,
            canonical_bundle_path=record.bundle_path,
            version_id=version_id,
        )
        self._get_registry().touch_project(project_id)
        return active_state

    def get_run_detail(self, project_id: str, run_id: str) -> dict[str, Any]:
        record = self._get_registry().get_project(project_id)
        run_record = self._get_run_store().get_run(record.canonical_root, run_id)
        log_text = self._get_run_store().read_log(run_record)
        return {
            "run": run_record.to_dict(),
            "log": log_text,
        }

    @staticmethod
    def _build_node_detail_payload(
        *,
        bundle,
        node_type: str,
        node_key: str,
        active_version_id: str | None,
    ) -> dict[str, Any]:
        if node_type == "characters":
            return {
                "node_id": "characters:project",
                "node_type": node_type,
                "node_key": node_key,
                "title": "角色资产",
                "active_version_id": active_version_id,
                "payload": {
                    "characters": [character.to_dict() for character in bundle.characters],
                    "assets": [asset.to_dict() for asset in bundle.assets],
                },
            }

        if node_type == "build_cards":
            return {
                "node_id": "build_cards:project",
                "node_type": node_type,
                "node_key": node_key,
                "title": "执行卡",
                "active_version_id": active_version_id,
                "payload": {
                    "workflow_cards": [card.to_dict() for card in bundle.workflow_cards],
                },
            }

        if node_type == "export":
            return {
                "node_id": "export:project",
                "node_type": node_type,
                "node_key": node_key,
                "title": "项目导出",
                "active_version_id": active_version_id,
                "payload": {
                    "manifest": bundle.manifest.to_dict() if bundle.manifest else None,
                    "assets": [asset.to_dict() for asset in bundle.assets],
                },
            }

        shot = bundle.find_shot(node_key)
        if shot is None:
            raise KeyError(f"未找到节点对应镜头：{node_key}")
        return {
            "node_id": f"{node_type}:{node_key}",
            "node_type": node_type,
            "node_key": node_key,
            "title": shot.title,
            "active_version_id": active_version_id,
            "payload": {
                "shot": shot.to_dict(),
                "related_cards": [
                    card.to_dict()
                    for card in bundle.workflow_cards
                    if card.shot_id == node_key
                ],
            },
        }

    def _build_project_summary(self, record: SproutImportedProjectRecord) -> dict[str, Any]:
        return self._get_adapter().build_project_summary(record)

    @staticmethod
    def _build_node_summaries(
        bundle,
        versions,
    ) -> list[dict[str, Any]]:
        version_map = {}
        for version in versions:
            version_map.setdefault((version.node_type, version.node_key), []).append(version.version_id)

        nodes: list[dict[str, Any]] = [
            {
                "node_id": "characters:project",
                "node_type": "characters",
                "node_key": "project",
                "title": "角色资产",
                "status": (
                    "generated"
                    if bundle.characters and all(character.reference_assets for character in bundle.characters)
                    else "pending"
                ),
                "version_ids": version_map.get(("characters", "project"), []),
            },
            {
                "node_id": "build_cards:project",
                "node_type": "build_cards",
                "node_key": "project",
                "title": "执行卡",
                "status": "ready" if bundle.workflow_cards else "pending",
                "version_ids": version_map.get(("build_cards", "project"), []),
            },
            {
                "node_id": "export:project",
                "node_type": "export",
                "node_key": "project",
                "title": "项目导出",
                "status": bundle.manifest.status if bundle.manifest else "draft",
                "version_ids": version_map.get(("export", "project"), []),
            },
        ]
        for shot in bundle.shots:
            nodes.append(
                {
                    "node_id": f"prepare_shot:{shot.shot_id}",
                    "node_type": "prepare_shot",
                    "node_key": shot.shot_id,
                    "title": f"{shot.title} - Prompt 准备",
                    "status": shot.status if shot.status in {"prompt_ready", "generated"} else "pending",
                    "version_ids": version_map.get(("prepare_shot", shot.shot_id), []),
                }
            )
            nodes.append(
                {
                    "node_id": f"generate_shot:{shot.shot_id}",
                    "node_type": "generate_shot",
                    "node_key": shot.shot_id,
                    "title": f"{shot.title} - 视频生成",
                    "status": "generated" if shot.output_assets else "pending",
                    "version_ids": version_map.get(("generate_shot", shot.shot_id), []),
                }
            )
        return nodes

    def _get_adapter(self) -> SproutProjectAdapter:
        if self.adapter is None:
            self.adapter = SproutProjectAdapter()
        return self.adapter

    def _get_registry(self) -> SproutProjectRegistry:
        if self.registry is None:
            self.registry = SproutProjectRegistry()
        return self.registry

    def _get_version_store(self) -> SproutVersionStore:
        if self.version_store is None:
            self.version_store = SproutVersionStore()
        return self.version_store

    def _get_run_store(self) -> SproutRunStore:
        if self.run_store is None:
            self.run_store = SproutRunStore()
        return self.run_store

    def _get_project_store(self) -> SproutProjectStore:
        if self.project_store is None:
            self.project_store = SproutProjectStore()
        return self.project_store
