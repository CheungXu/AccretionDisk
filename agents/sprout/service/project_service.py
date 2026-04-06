"""Sprout 项目查询与导入服务。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..core.final_output import (
    find_final_video_asset,
    get_existing_final_video_path,
    get_final_video_output_path,
)
from ..core.shared import read_json_file
from ..core.storage import SproutProjectStore
from .adapters import SproutProjectAdapter
from .registry import SproutProjectRegistry
from .runtime import SproutRunStore, SproutVersionStore
from .types import SproutImportedProjectRecord
from .workflow_nodes import (
    build_node_id,
    build_workflow_node_specs,
    get_node_type_label,
    is_empty_project_placeholder,
)


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
        versions, active_state = self._load_versions_and_active_state(record, bundle=bundle)
        return {
            "project": self._build_project_summary(record),
            "bundle": bundle.to_dict(),
            "manifest": manifest_payload if isinstance(manifest_payload, dict) else {},
            "nodes": self._build_workflow_nodes(
                bundle=bundle,
                project_root=record.canonical_root,
                versions=versions,
                active_state=active_state,
            ),
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
        bundle = self._get_project_store().load_bundle(record.bundle_path)
        versions, _ = self._load_versions_and_active_state(record, bundle=bundle)
        versions = [
            version
            for version in versions
            if (node_type is None or version.node_type == node_type)
            and (node_key is None or version.node_key == node_key)
        ]
        return [version.to_dict() for version in versions]

    def get_version_detail(self, project_id: str, version_id: str) -> dict[str, Any]:
        record = self._get_registry().get_project(project_id)
        bundle = self._get_project_store().load_bundle(record.bundle_path)
        versions, _ = self._load_versions_and_active_state(record, bundle=bundle)
        if any(version.version_id == version_id for version in versions):
            return self._get_version_store().get_version_detail(record.canonical_root, version_id)
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
        all_versions, active_state = self._load_versions_and_active_state(record, bundle=bundle)
        versions = [
            version
            for version in all_versions
            if version.node_type == node_type and version.node_key == node_key
        ]
        runs = self._get_run_store().list_runs(
            record.canonical_root,
            node_type=node_type,
            node_key=node_key,
        )
        workflow_nodes = self._build_workflow_nodes(
            bundle=bundle,
            project_root=record.canonical_root,
            versions=all_versions,
            active_state=active_state,
        )
        node_id = build_node_id(node_type, node_key)
        node_summary = next((node for node in workflow_nodes if node["node_id"] == node_id), None)
        if node_summary is None:
            raise KeyError(f"未找到节点：{node_id}")

        return {
            "project": self._build_project_summary(record),
            "node": {
                **node_summary,
                "payload": self._build_node_payload(
                    bundle=bundle,
                    output_root=record.canonical_root,
                    node_type=node_type,
                    node_key=node_key,
                ),
            },
            "versions": [version.to_dict() for version in versions],
            "runs": [run.to_dict() for run in runs],
            "active_state": active_state,
        }

    def activate_version(self, project_id: str, version_id: str) -> dict[str, Any]:
        record = self._get_registry().get_project(project_id)
        bundle = self._get_project_store().load_bundle(record.bundle_path)
        self._load_versions_and_active_state(record, bundle=bundle)
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
    def _build_node_payload(
        *,
        bundle,
        output_root: str | Path | None,
        node_type: str,
        node_key: str,
    ) -> dict[str, Any]:
        if node_type == "user_input":
            return {
                "topic_input": bundle.topic_input.to_dict(),
                "source_storyboard": bundle.source_storyboard,
                "project_name": bundle.project_name,
                "episode": bundle.episode.to_dict(),
                "is_placeholder": is_empty_project_placeholder(bundle),
                "has_planning_content": bool(bundle.characters or bundle.shots),
            }

        if node_type == "characters":
            return {
                "characters": [character.to_dict() for character in bundle.characters],
                "assets": [asset.to_dict() for asset in bundle.assets],
            }

        if node_type == "build_cards":
            return {
                "workflow_cards": [card.to_dict() for card in bundle.workflow_cards],
            }

        if node_type == "export":
            return {
                "manifest": bundle.manifest.to_dict() if bundle.manifest else None,
                "assets": [asset.to_dict() for asset in bundle.assets],
            }

        if node_type == "final_output":
            final_asset = find_final_video_asset(bundle)
            final_video_path = get_existing_final_video_path(bundle, output_root=output_root)
            final_asset_payload = final_asset.to_dict() if final_asset is not None else None
            if final_asset_payload is None and final_video_path is not None:
                final_asset_payload = {
                    "asset_id": f"{bundle.project_name}_final_video",
                    "asset_type": "final_video",
                    "source": "final_output",
                    "path": str(final_video_path),
                }
            return {
                "asset": final_asset_payload,
                "expected_path": (
                    str(get_final_video_output_path(output_root, bundle.project_name))
                    if output_root is not None
                    else None
                ),
                "segment_count": len(bundle.shots),
                "completed_segments": sum(
                    1
                    for shot in bundle.shots
                    if any(asset.asset_type == "shot_video" and asset.path for asset in shot.output_assets)
                ),
                "resolution_report": (
                    final_asset_payload.get("metadata", {}).get("resolution_report")
                    if isinstance(final_asset_payload, dict)
                    else None
                ),
            }

        shot = bundle.find_shot(node_key)
        if shot is None:
            raise KeyError(f"未找到节点对应镜头：{node_key}")
        return {
            "shot": shot.to_dict(),
            "related_cards": [
                card.to_dict()
                for card in bundle.workflow_cards
                if card.shot_id == node_key
            ],
        }

    def _build_project_summary(self, record: SproutImportedProjectRecord) -> dict[str, Any]:
        return self._get_adapter().build_project_summary(record)

    def _load_versions_and_active_state(
        self,
        record: SproutImportedProjectRecord,
        *,
        bundle,
    ) -> tuple[list[Any], dict[str, Any]]:
        version_store = self._get_version_store()
        versions = version_store.list_versions(record.canonical_root)
        active_state = version_store.get_active_state(record.canonical_root)
        if versions:
            return versions, active_state

        return version_store.bootstrap_versions_from_project_files(
            project_root=record.canonical_root,
            project_bundle=bundle,
            project_id=record.project_id,
            bundle_path=record.bundle_path,
        )

    def _build_workflow_nodes(
        self,
        *,
        bundle,
        project_root: str | Path,
        versions,
        active_state: dict[str, Any],
    ) -> list[dict[str, Any]]:
        version_records_by_node: dict[str, list[Any]] = {}
        version_by_id: dict[str, Any] = {}
        for version in versions:
            node_id = build_node_id(version.node_type, version.node_key)
            version_records_by_node.setdefault(node_id, []).append(version)
            version_by_id[version.version_id] = version

        raw_selected_versions = active_state.get("selected_versions", {})
        selected_versions = raw_selected_versions if isinstance(raw_selected_versions, dict) else {}
        workflow_nodes: list[dict[str, Any]] = []
        current_dependency_versions: dict[str, str] = {}

        for node_spec in build_workflow_node_specs(bundle):
            node_id = node_spec["node_id"]
            node_type = node_spec["node_type"]
            node_key = node_spec["node_key"]
            version_records = version_records_by_node.get(node_id, [])
            active_version_id = self._normalize_active_version_id(selected_versions.get(node_id))
            active_version = version_by_id.get(active_version_id) if active_version_id else None
            base_status = self._get_base_status(
                bundle,
                project_root=project_root,
                node_type=node_type,
                node_key=node_key,
            )
            upstream_node = workflow_nodes[-1] if workflow_nodes else None
            status, status_reason, is_current_complete, effective_version_id = self._resolve_node_status(
                node_type=node_type,
                base_status=base_status,
                active_version=active_version,
                current_dependency_versions=current_dependency_versions,
                upstream_node=upstream_node,
                workflow_nodes=workflow_nodes,
                has_versions=bool(version_records),
            )
            workflow_node = {
                **node_spec,
                "type_label": get_node_type_label(node_type),
                "status": status,
                "status_reason": status_reason,
                "active_version_id": active_version_id,
                "upstream_node_id": upstream_node["node_id"] if upstream_node else None,
                "upstream_version_id": upstream_node["effective_version_id"] if upstream_node else None,
                "version_ids": [version.version_id for version in version_records],
                "is_current_complete": is_current_complete,
                "effective_version_id": effective_version_id,
            }
            workflow_nodes.append(workflow_node)
            if is_current_complete and effective_version_id:
                current_dependency_versions[node_id] = effective_version_id

        return [self._strip_runtime_fields(node) for node in workflow_nodes]

    @staticmethod
    def _normalize_active_version_id(value: Any) -> str | None:
        if value is None:
            return None
        normalized_value = str(value).strip()
        return normalized_value or None

    @staticmethod
    def _get_base_status(
        bundle,
        *,
        project_root: str | Path,
        node_type: str,
        node_key: str,
    ) -> str:
        if node_type == "user_input":
            topic_text = str(bundle.topic_input.topic or "").strip()
            storyboard_text = str(bundle.source_storyboard or "").strip()
            if topic_text or storyboard_text:
                return "ready"
            if is_empty_project_placeholder(bundle):
                return "pending"
            return "ready"
        if node_type == "characters":
            return (
                "generated"
                if bundle.characters and all(character.reference_assets for character in bundle.characters)
                else "pending"
            )
        if node_type == "build_cards":
            return "ready" if bundle.workflow_cards else "pending"
        if node_type == "export":
            if bundle.manifest is None:
                return "pending"
            return bundle.manifest.status or "ready"
        if node_type == "final_output":
            return "ready" if get_existing_final_video_path(bundle, output_root=project_root) else "pending"

        shot = bundle.find_shot(node_key)
        if shot is None:
            raise KeyError(f"未找到节点对应镜头：{node_key}")
        if node_type == "prepare_shot":
            return "prompt_ready" if shot.status in {"prompt_ready", "generated"} else "pending"
        if node_type == "generate_shot":
            return "generated" if shot.output_assets else "pending"
        raise KeyError(f"未知节点类型：{node_type}")

    def _resolve_node_status(
        self,
        *,
        node_type: str,
        base_status: str,
        active_version,
        current_dependency_versions: dict[str, str],
        upstream_node: dict[str, Any] | None,
        workflow_nodes: list[dict[str, Any]],
        has_versions: bool,
    ) -> tuple[str, str, bool, str | None]:
        completed_status = self._get_completed_status(node_type=node_type, base_status=base_status)
        base_is_complete = self._is_complete_status(base_status)

        if upstream_node is None:
            if active_version is not None:
                return completed_status, "当前节点已经生成，并已设为当前激活版本。", True, active_version.version_id
            if base_is_complete:
                return completed_status, "沿用项目当前已有结果。", True, None
            return "pending", "当前节点尚未生成。", False, None

        if not upstream_node["is_current_complete"]:
            return (
                "waiting",
                f"等待上游节点“{upstream_node['title']}”完成后再继续。",
                False,
                None,
            )

        if active_version is not None:
            dependency_version_ids = dict(active_version.dependency_version_ids)
            if dependency_version_ids == current_dependency_versions:
                return completed_status, "当前结果与上游当前版本链一致。", True, active_version.version_id
            stale_node_title = self._find_stale_upstream_title(
                active_version=active_version,
                current_dependency_versions=current_dependency_versions,
                workflow_upstream_nodes=workflow_nodes,
            )
            if stale_node_title:
                return (
                    "pending",
                    f"上游版本已更新，当前节点需要基于新的“{stale_node_title}”重新生成。",
                    False,
                    None,
                )
            return "pending", "上游版本链已变化，当前节点需要重新生成。", False, None

        if base_is_complete and not has_versions and not current_dependency_versions:
            return completed_status, "沿用项目当前已有结果。", True, None

        if base_is_complete and not has_versions:
            return "pending", "当前节点已有旧结果，但还没有和当前上游版本建立对应关系。", False, None

        return (
            "pending",
            f"上游节点“{upstream_node['title']}”已就绪，当前节点待执行。",
            False,
            None,
        )

    @staticmethod
    def _find_stale_upstream_title(
        *,
        active_version,
        current_dependency_versions: dict[str, str],
        workflow_upstream_nodes: list[dict[str, Any]],
    ) -> str | None:
        dependency_version_ids = dict(active_version.dependency_version_ids)
        for upstream_node in reversed(workflow_upstream_nodes):
            node_id = upstream_node["node_id"]
            expected_version_id = current_dependency_versions.get(node_id)
            current_version_id = dependency_version_ids.get(node_id)
            if expected_version_id != current_version_id:
                node_title = upstream_node.get("title")
                return str(node_title) if node_title else node_id
        return None

    @staticmethod
    def _get_completed_status(*, node_type: str, base_status: str) -> str:
        completed_status_by_node_type = {
            "user_input": "ready",
            "characters": "generated",
            "prepare_shot": "prompt_ready",
            "generate_shot": "generated",
            "build_cards": "ready",
            "export": "ready",
            "final_output": "ready",
        }
        return completed_status_by_node_type.get(node_type, base_status or "ready")

    @staticmethod
    def _is_complete_status(status: str) -> bool:
        return status in {"generated", "prompt_ready", "ready", "success"}

    @staticmethod
    def _strip_runtime_fields(node_payload: dict[str, Any]) -> dict[str, Any]:
        return {
            key: value
            for key, value in node_payload.items()
            if key not in {"is_current_complete", "effective_version_id"}
        }

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
