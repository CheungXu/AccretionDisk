"""Sprout 节点执行服务。"""

from __future__ import annotations

from dataclasses import dataclass

from ..core.orchestration import SproutWorkflow
from ..core.storage import SproutProjectStore
from .registry import SproutProjectRegistry
from .runtime import SproutRunStore, SproutVersionStore


@dataclass
class SproutWorkflowService:
    """负责执行一期后端可控节点。"""

    registry: SproutProjectRegistry | None = None
    version_store: SproutVersionStore | None = None
    run_store: SproutRunStore | None = None
    project_store: SproutProjectStore | None = None

    def run_node(
        self,
        *,
        project_id: str,
        node_type: str,
        node_key: str = "project",
        source_version_id: str | None = None,
        force: bool = False,
        extra_reference_count: int = 0,
    ) -> dict[str, object]:
        record = self._get_registry().get_project(project_id)
        normalized_node_type = self._normalize_node_type(node_type)
        bundle = (
            self._get_version_store().load_bundle_for_version(record.canonical_root, source_version_id)
            if source_version_id
            else self._get_project_store().load_bundle(record.bundle_path)
        )
        run_record = self._get_run_store().start_run(
            project_root=record.canonical_root,
            project_id=project_id,
            node_type=normalized_node_type,
            node_key=node_key,
            source_version_id=source_version_id,
            shot_ids=[node_key] if normalized_node_type in {"prepare_shot", "generate_shot"} else None,
        )
        workflow = SproutWorkflow()
        try:
            self._get_run_store().append_log(
                project_root=record.canonical_root,
                run_record=run_record,
                message=f"执行节点类型：{normalized_node_type}，节点键：{node_key}。",
            )
            if source_version_id:
                self._get_run_store().append_log(
                    project_root=record.canonical_root,
                    run_record=run_record,
                    message=f"使用来源版本：{source_version_id}。",
                )

            if normalized_node_type == "characters":
                workflow.build_characters(
                    project_bundle=bundle,
                    output_root=record.canonical_root,
                    extra_reference_count=extra_reference_count,
                    skip_existing=not force,
                )
            elif normalized_node_type == "prepare_shot":
                self._validate_shot_node_key(node_key)
                workflow.prepare_shots(
                    project_bundle=bundle,
                    output_root=record.canonical_root,
                    shot_ids=[node_key],
                )
            elif normalized_node_type == "generate_shot":
                self._validate_shot_node_key(node_key)
                workflow.generate_shots(
                    project_bundle=bundle,
                    output_root=record.canonical_root,
                    shot_ids=[node_key],
                    skip_existing=not force,
                )
            elif normalized_node_type == "build_cards":
                workflow.build_workflow_cards(
                    project_bundle=bundle,
                    output_root=record.canonical_root,
                )
            elif normalized_node_type == "export":
                workflow.export_bundle(
                    project_bundle=bundle,
                    output_root=record.canonical_root,
                )
            else:
                raise ValueError(f"暂不支持的节点类型：{node_type}")

            version_record = self._get_version_store().create_version(
                project_root=record.canonical_root,
                project_bundle=bundle,
                project_id=project_id,
                node_type=normalized_node_type,
                node_key=node_key,
                source_version_id=source_version_id,
                run_id=run_record.run_id,
                shot_ids=[node_key] if normalized_node_type in {"prepare_shot", "generate_shot"} else None,
                notes=[f"force={force}"],
            )
            active_state = self._get_version_store().activate_version(
                project_root=record.canonical_root,
                canonical_bundle_path=record.bundle_path,
                version_id=version_record.version_id,
            )
            self._get_registry().touch_project(project_id)
            self._get_run_store().finish_run(
                project_root=record.canonical_root,
                run_record=run_record,
                status="success",
                result_version_id=version_record.version_id,
            )
            return {
                "run": run_record.to_dict(),
                "version": version_record.to_dict(),
                "active_state": active_state,
            }
        except Exception as exc:
            self._get_run_store().finish_run(
                project_root=record.canonical_root,
                run_record=run_record,
                status="failed",
                error_message=str(exc),
            )
            raise

    @staticmethod
    def _normalize_node_type(node_type: str) -> str:
        normalized_value = node_type.strip().lower()
        aliases = {
            "build_characters": "characters",
            "prepare_shots": "prepare_shot",
            "generate_shots": "generate_shot",
            "build_cards": "build_cards",
        }
        return aliases.get(normalized_value, normalized_value)

    @staticmethod
    def _validate_shot_node_key(node_key: str) -> None:
        if not node_key or node_key == "project":
            raise ValueError("镜头节点必须提供具体 shot_id。")

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
