"""Sprout 项目查询服务（纯云端模式）。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..core.final_output import find_final_video_asset
from ..core.models import SproutProjectBundle
from .cloud_project_store import SproutCloudProjectStore
from .cloud_run_store import SproutCloudRunStore
from .cloud_version_store import SproutCloudVersionStore
from .types import SproutImportedProjectRecord, SproutRunRecord
from .workflow_nodes import (
    PROJECT_NODE_KEY,
    SCRIPT_STORYBOARD_NODE_TYPE,
    build_node_id,
    build_workflow_node_specs,
    get_node_spec,
    get_node_type_label,
    get_upstream_node_ids,
    is_empty_project_placeholder,
)


@dataclass
class SproutProjectService:
    """负责项目查询与激活版本切换（纯云端模式）。"""

    cloud_project_store: SproutCloudProjectStore | None = None
    cloud_version_store: SproutCloudVersionStore | None = None
    cloud_run_store: SproutCloudRunStore | None = None

    # ------------------------------------------------------------------
    # 公开 API（面向用户鉴权层）
    # ------------------------------------------------------------------

    def list_projects_for_user(self, user_id: str) -> list[dict[str, Any]]:
        """按登录用户列出云端项目。"""

        project_rows = self._get_cloud_project_store().list_projects_for_user(user_id)
        return [self._build_project_summary_from_cloud_row(row) for row in project_rows]

    def get_project_detail_for_user(self, user_id: str, project_id: str) -> dict[str, Any]:
        """按登录用户读取项目详情。"""

        record = self.get_accessible_project_record_for_user(user_id, project_id)
        return self._get_project_detail_from_record(record)

    def get_project_role_for_user(self, user_id: str, project_id: str) -> str:
        """获取用户在项目中的角色。"""

        membership = self._get_cloud_project_store().get_project_member(
            project_id=project_id,
            user_id=user_id,
        )
        if not isinstance(membership, dict):
            raise PermissionError("当前用户无权访问该项目。")
        role = str(membership.get("role") or "").strip()
        if not role:
            raise PermissionError("当前用户缺少项目角色。")
        return role

    def get_accessible_project_record_for_user(self, user_id: str, project_id: str) -> SproutImportedProjectRecord:
        """返回用户可访问的项目记录。"""

        membership = self._get_cloud_project_store().get_project_member(
            project_id=project_id,
            user_id=user_id,
        )
        if not isinstance(membership, dict):
            raise PermissionError("当前用户无权访问该项目。")
        project_row = self._get_cloud_project_store().get_project_row(project_id)
        if not isinstance(project_row, dict):
            raise KeyError(f"未找到项目：{project_id}")
        return self._get_cloud_project_store().build_record_from_project_row(project_row)

    def get_project_summary_for_user(self, user_id: str, project_id: str) -> dict[str, Any]:
        """读取用户可访问的项目摘要。"""

        record = self.get_accessible_project_record_for_user(user_id, project_id)
        return self._build_project_summary(record)

    def list_versions_for_user(
        self,
        user_id: str,
        project_id: str,
        *,
        node_type: str | None = None,
        node_key: str | None = None,
    ) -> list[dict[str, Any]]:
        """按登录用户读取版本列表。"""

        record = self.get_accessible_project_record_for_user(user_id, project_id)
        return self._list_versions_from_record(record, node_type=node_type, node_key=node_key)

    def get_version_detail_for_user(self, user_id: str, project_id: str, version_id: str) -> dict[str, Any]:
        """按登录用户读取版本详情。"""

        record = self.get_accessible_project_record_for_user(user_id, project_id)
        return self._get_version_detail_from_record(record, version_id)

    def get_node_detail_for_user(
        self,
        user_id: str,
        project_id: str,
        *,
        node_type: str,
        node_key: str,
    ) -> dict[str, Any]:
        """按登录用户读取节点详情。"""

        record = self.get_accessible_project_record_for_user(user_id, project_id)
        return self._get_node_detail_from_record(record, node_type=node_type, node_key=node_key)

    def activate_version_for_user(self, user_id: str, project_id: str, version_id: str) -> dict[str, Any]:
        """按登录用户切换激活版本。"""

        record = self.get_accessible_project_record_for_user(user_id, project_id)
        return self._activate_version_from_record(record, version_id)

    def get_run_detail_for_user(self, user_id: str, project_id: str, run_id: str) -> dict[str, Any]:
        """按登录用户读取运行详情。"""

        record = self.get_accessible_project_record_for_user(user_id, project_id)
        return self._get_run_detail_from_record(record, run_id)

    # ------------------------------------------------------------------
    # 内部实现：项目详情
    # ------------------------------------------------------------------

    def _get_project_detail_from_record(self, record: SproutImportedProjectRecord) -> dict[str, Any]:
        """从云端获取项目详情。"""

        payload = self._get_cloud_project_store().download_latest_bundle_snapshot(record.project_id)
        if not payload:
            raise KeyError(f"未找到项目 bundle 快照：{record.project_id}")
        bundle = SproutProjectBundle.from_dict(payload)

        versions, active_state = self._load_versions_and_active_state(record.project_id)
        return {
            "project": self._build_project_summary(record, bundle=bundle),
            "bundle": bundle.to_dict(),
            "manifest": bundle.manifest.to_dict() if bundle.manifest else {},
            "nodes": self._build_workflow_nodes(
                bundle=bundle,
                versions=versions,
                active_state=active_state,
            ),
            "versions": [version.to_dict() for version in versions],
            "active_state": active_state,
        }

    # ------------------------------------------------------------------
    # 内部实现：版本列表 / 详情
    # ------------------------------------------------------------------

    def _list_versions_from_record(
        self,
        record: SproutImportedProjectRecord,
        *,
        node_type: str | None = None,
        node_key: str | None = None,
    ) -> list[dict[str, Any]]:
        """从云端获取版本列表。"""

        payload = self._get_cloud_project_store().download_latest_bundle_snapshot(record.project_id)
        if not payload:
            raise KeyError(f"未找到项目 bundle 快照：{record.project_id}")
        bundle = SproutProjectBundle.from_dict(payload)

        versions, _ = self._load_versions_and_active_state(record.project_id)
        if node_type == SCRIPT_STORYBOARD_NODE_TYPE:
            source_node_type, source_node_key = self._split_node_id(
                self._resolve_version_source_node_id(
                    bundle,
                    node_type=node_type,
                    node_key=node_key or PROJECT_NODE_KEY,
                )
            )
            node_type = source_node_type
            node_key = source_node_key
        versions = [
            version
            for version in versions
            if (node_type is None or version.node_type == node_type)
            and (node_key is None or version.node_key == node_key)
        ]
        return [version.to_dict() for version in versions]

    def _get_version_detail_from_record(
        self,
        record: SproutImportedProjectRecord,
        version_id: str,
    ) -> dict[str, Any]:
        """从云端获取版本详情。"""

        cloud_version_store = self._get_cloud_version_store()
        version_row = cloud_version_store.get_version_row(version_id)
        if version_row is None:
            raise KeyError(f"未找到版本：{version_id}")
        version_record = cloud_version_store.build_version_record_from_row(version_row)

        snapshot_payload = None
        snapshot_id = version_row.get("snapshot_id")
        if snapshot_id:
            try:
                snapshot_payload = self._get_cloud_project_store().download_snapshot(
                    snapshot_id, record.project_id
                )
            except Exception:
                snapshot_payload = None

        return {
            "version": version_record.to_dict(),
            "snapshot": snapshot_payload,
        }

    # ------------------------------------------------------------------
    # 内部实现：节点详情
    # ------------------------------------------------------------------

    def _get_node_detail_from_record(
        self,
        record: SproutImportedProjectRecord,
        *,
        node_type: str,
        node_key: str,
    ) -> dict[str, Any]:
        """从云端获取节点详情。"""

        payload = self._get_cloud_project_store().download_latest_bundle_snapshot(record.project_id)
        if not payload:
            raise KeyError(f"未找到项目 bundle 快照：{record.project_id}")
        bundle = SproutProjectBundle.from_dict(payload)

        all_versions, active_state = self._load_versions_and_active_state(record.project_id)
        version_source_node_type, version_source_node_key = self._split_node_id(
            self._resolve_version_source_node_id(bundle, node_type=node_type, node_key=node_key)
        )
        filtered_versions = [
            version
            for version in all_versions
            if version.node_type == version_source_node_type and version.node_key == version_source_node_key
        ]

        cloud_run_store = self._get_cloud_run_store()
        run_rows = cloud_run_store.list_project_runs(
            record.project_id,
            node_type=version_source_node_type,
            node_key=version_source_node_key,
        )
        runs = [self._build_run_record_from_row(row) for row in run_rows]

        workflow_nodes = self._build_workflow_nodes(
            bundle=bundle,
            versions=all_versions,
            active_state=active_state,
        )
        node_id = build_node_id(node_type, node_key)
        node_summary = next((node for node in workflow_nodes if node["node_id"] == node_id), None)
        if node_summary is None:
            raise KeyError(f"未找到节点：{node_id}")

        return {
            "project": self._build_project_summary(record, bundle=bundle),
            "node": {
                **node_summary,
                "payload": self._build_node_payload(
                    bundle=bundle,
                    node_type=node_type,
                    node_key=node_key,
                ),
            },
            "versions": [version.to_dict() for version in filtered_versions],
            "runs": [run.to_dict() for run in runs],
            "active_state": active_state,
        }

    # ------------------------------------------------------------------
    # 内部实现：版本激活
    # ------------------------------------------------------------------

    def _activate_version_from_record(
        self,
        record: SproutImportedProjectRecord,
        version_id: str,
    ) -> dict[str, Any]:
        """从云端切换激活版本。"""

        cloud_version_store = self._get_cloud_version_store()
        version_row = cloud_version_store.get_version_row(version_id)
        if version_row is None:
            raise KeyError(f"未找到版本：{version_id}")
        version_record = cloud_version_store.build_version_record_from_row(version_row)

        cloud_project_store = self._get_cloud_project_store()
        active_state = cloud_project_store.get_active_state(record.project_id)

        node_id = build_node_id(version_record.node_type, version_record.node_key)
        selected_versions = active_state.get("selected_versions", {})
        if not isinstance(selected_versions, dict):
            selected_versions = {}
        selected_versions[node_id] = version_id
        active_state["selected_versions"] = selected_versions
        active_state["active_bundle_version_id"] = version_id

        snapshot_id = version_row.get("snapshot_id")
        if snapshot_id:
            active_state["active_bundle_snapshot_id"] = snapshot_id

        cloud_project_store.update_active_state(record.project_id, active_state)
        return active_state

    # ------------------------------------------------------------------
    # 内部实现：运行详情
    # ------------------------------------------------------------------

    def _get_run_detail_from_record(
        self,
        record: SproutImportedProjectRecord,
        run_id: str,
    ) -> dict[str, Any]:
        """从云端获取运行详情及日志。"""

        cloud_run_store = self._get_cloud_run_store()
        run_rows = cloud_run_store.list_project_runs(record.project_id)
        run_row = next((row for row in run_rows if row.get("run_id") == run_id), None)
        if run_row is None:
            raise KeyError(f"未找到运行记录：{run_id}")

        run_record = self._build_run_record_from_row(run_row)

        log_text = ""
        log_object_path = str(run_row.get("log_object_path") or "").strip()
        if log_object_path:
            try:
                storage_service = cloud_run_store._get_storage_service()  # noqa: SLF001
                raw_bytes = storage_service.download_object(object_path=log_object_path)
                log_text = raw_bytes.decode("utf-8")
            except Exception:
                log_text = ""

        return {
            "run": run_record.to_dict(),
            "log": log_text,
        }

    # ------------------------------------------------------------------
    # 摘要构建
    # ------------------------------------------------------------------

    def _build_project_summary(
        self,
        record: SproutImportedProjectRecord,
        *,
        bundle: SproutProjectBundle | None = None,
    ) -> dict[str, Any]:
        """构建项目摘要。若传入 bundle 则直接使用，否则尝试从云端下载。"""

        summary: dict[str, Any] = {
            "project_id": record.project_id,
            "project_type": record.project_type,
            "display_name": record.display_name,
            "project_name": record.project_name,
            "health_status": record.health_status,
            "import_mode": record.import_mode,
            "imported_at": record.imported_at,
            "last_active_at": record.last_active_at,
            "notes": list(record.notes),
        }

        if bundle is None:
            try:
                payload = self._get_cloud_project_store().download_latest_bundle_snapshot(record.project_id)
                if payload:
                    bundle = SproutProjectBundle.from_dict(payload)
            except Exception:
                pass

        if bundle is not None:
            summary["episode"] = bundle.episode.to_dict()
            summary["topic_input"] = bundle.topic_input.to_dict()
            summary["character_count"] = len(bundle.characters)
            summary["shot_count"] = len(bundle.shots)
            summary["manifest"] = bundle.manifest.to_dict() if bundle.manifest else {}
        else:
            summary["episode"] = {}
            summary["topic_input"] = {}
            summary["character_count"] = 0
            summary["shot_count"] = 0
            summary["manifest"] = {}

        return summary

    def _build_project_summary_from_cloud_row(self, project_row: dict[str, Any]) -> dict[str, Any]:
        """从云端项目行直接构建摘要（不下载 bundle）。"""

        summary: dict[str, Any] = {
            "project_id": project_row.get("project_id"),
            "project_type": project_row.get("project_type"),
            "display_name": project_row.get("display_name"),
            "project_name": project_row.get("project_name"),
            "health_status": project_row.get("health_status"),
            "import_mode": project_row.get("import_mode"),
            "imported_at": project_row.get("imported_at"),
            "last_active_at": project_row.get("last_active_at"),
            "manifest": {},
            "episode": {"title": project_row.get("title")},
            "topic_input": {"topic": project_row.get("topic")},
            "character_count": 0,
            "shot_count": 0,
        }
        summary["current_user_role"] = project_row.get("current_user_role")
        return summary

    # ------------------------------------------------------------------
    # 版本与激活状态加载
    # ------------------------------------------------------------------

    def _load_versions_and_active_state(
        self,
        project_id: str,
    ) -> tuple[list[Any], dict[str, Any]]:
        """从云端加载版本列表和激活状态。"""

        cloud_version_store = self._get_cloud_version_store()
        version_rows = cloud_version_store.list_project_versions(project_id)
        versions = [cloud_version_store.build_version_record_from_row(row) for row in version_rows]
        active_state = self._get_cloud_project_store().get_active_state(project_id)
        return versions, active_state

    # ------------------------------------------------------------------
    # 工作流节点构建（核心业务逻辑）
    # ------------------------------------------------------------------

    def _build_workflow_nodes(
        self,
        *,
        bundle,
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
        workflow_node_by_id: dict[str, dict[str, Any]] = {}
        current_dependency_versions: dict[str, str] = {}

        for node_spec in build_workflow_node_specs(bundle):
            node_id = node_spec["node_id"]
            node_type = node_spec["node_type"]
            node_key = node_spec["node_key"]
            version_source_node_id = str(node_spec.get("version_source_node_id") or node_id)
            version_records = version_records_by_node.get(version_source_node_id, [])
            active_version_id = self._normalize_active_version_id(selected_versions.get(version_source_node_id))
            active_version = version_by_id.get(active_version_id) if active_version_id else None
            base_status = self._get_base_status(
                bundle,
                node_type=node_type,
                node_key=node_key,
            )
            direct_upstream_node_ids = [
                str(item).strip()
                for item in node_spec.get("upstream_node_ids", [])
                if str(item).strip()
            ]
            direct_upstream_nodes = [
                workflow_node_by_id[upstream_node_id]
                for upstream_node_id in direct_upstream_node_ids
                if upstream_node_id in workflow_node_by_id
            ]
            ancestor_node_ids = get_upstream_node_ids(bundle, node_type, node_key)
            ancestor_nodes = [
                workflow_node_by_id[ancestor_node_id]
                for ancestor_node_id in ancestor_node_ids
                if ancestor_node_id in workflow_node_by_id
            ]
            expected_dependency_versions = {
                ancestor_node_id: current_dependency_versions[ancestor_node_id]
                for ancestor_node_id in ancestor_node_ids
                if ancestor_node_id in current_dependency_versions
            }
            status, status_reason, is_current_complete, effective_version_id = self._resolve_node_status(
                node_type=node_type,
                base_status=base_status,
                active_version=active_version,
                expected_dependency_versions=expected_dependency_versions,
                direct_upstream_nodes=direct_upstream_nodes,
                ancestor_nodes=ancestor_nodes,
                has_versions=bool(version_records),
            )
            workflow_node = {
                **node_spec,
                "type_label": get_node_type_label(node_type),
                "status": status,
                "status_reason": status_reason,
                "active_version_id": active_version_id,
                "upstream_node_id": direct_upstream_node_ids[0] if direct_upstream_node_ids else None,
                "upstream_node_ids": direct_upstream_node_ids,
                "upstream_version_id": (
                    direct_upstream_nodes[0]["effective_version_id"] if direct_upstream_nodes else None
                ),
                "upstream_version_ids": [
                    upstream_node["effective_version_id"]
                    for upstream_node in direct_upstream_nodes
                    if upstream_node.get("effective_version_id")
                ],
                "version_ids": [version.version_id for version in version_records],
                "is_current_complete": is_current_complete,
                "effective_version_id": effective_version_id,
            }
            workflow_nodes.append(workflow_node)
            workflow_node_by_id[node_id] = workflow_node
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
        if node_type == SCRIPT_STORYBOARD_NODE_TYPE:
            return "ready" if bundle.shots else "pending"
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
            final_asset = find_final_video_asset(bundle)
            return "ready" if (final_asset is not None and final_asset.path) else "pending"

        shot = bundle.find_shot(node_key)
        if shot is None:
            raise KeyError(f"未找到节点对应镜头：{node_key}")
        if node_type == "prepare_shot":
            return "prompt_ready" if shot.status in {"prompt_ready", "generated"} else "pending"
        if node_type == "generate_shot":
            return "generated" if shot.output_assets else "pending"
        raise KeyError(f"未知节点类型：{node_type}")

    @staticmethod
    def _build_node_payload(
        *,
        bundle,
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

        if node_type == SCRIPT_STORYBOARD_NODE_TYPE:
            return {
                "topic_input": bundle.topic_input.to_dict(),
                "source_storyboard": bundle.source_storyboard,
                "episode": bundle.episode.to_dict(),
                "characters": [character.to_dict() for character in bundle.characters],
                "shots": [shot.to_dict() for shot in bundle.shots],
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
            final_asset_payload = final_asset.to_dict() if final_asset is not None else None
            return {
                "asset": final_asset_payload,
                "expected_path": None,
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

    # ------------------------------------------------------------------
    # 节点状态解析（核心业务逻辑）
    # ------------------------------------------------------------------

    def _resolve_node_status(
        self,
        *,
        node_type: str,
        base_status: str,
        active_version,
        expected_dependency_versions: dict[str, str],
        direct_upstream_nodes: list[dict[str, Any]],
        ancestor_nodes: list[dict[str, Any]],
        has_versions: bool,
    ) -> tuple[str, str, bool, str | None]:
        completed_status = self._get_completed_status(node_type=node_type, base_status=base_status)
        base_is_complete = self._is_complete_status(base_status)

        if not direct_upstream_nodes:
            if active_version is not None:
                return completed_status, "当前节点已经生成，并已设为当前激活版本。", True, active_version.version_id
            if base_is_complete:
                return completed_status, "沿用项目当前已有结果。", True, None
            return "pending", "当前节点尚未生成。", False, None

        blocked_upstream_node = next(
            (upstream_node for upstream_node in direct_upstream_nodes if not upstream_node["is_current_complete"]),
            None,
        )
        if blocked_upstream_node is not None:
            return (
                "waiting",
                f'等待上游节点"{blocked_upstream_node["title"]}"完成后再继续。',
                False,
                None,
            )

        if active_version is not None:
            dependency_version_ids = dict(active_version.dependency_version_ids)
            if dependency_version_ids == expected_dependency_versions:
                return completed_status, "当前结果与上游当前版本链一致。", True, active_version.version_id
            if not dependency_version_ids and base_is_complete:
                return completed_status, "沿用项目已有结果（旧版本无依赖追踪）。", True, active_version.version_id
            stale_node_title = self._find_stale_upstream_title(
                active_version=active_version,
                expected_dependency_versions=expected_dependency_versions,
                workflow_upstream_nodes=ancestor_nodes,
            )
            if stale_node_title:
                return (
                    "pending",
                    f'上游版本已更新，当前节点需要基于新的"{stale_node_title}"重新生成。',
                    False,
                    None,
                )
            return "pending", "上游版本链已变化，当前节点需要重新生成。", False, None

        if base_is_complete and not has_versions and not expected_dependency_versions:
            return completed_status, "沿用项目当前已有结果。", True, None

        if base_is_complete and not has_versions:
            return "pending", "当前节点已有旧结果，但还没有和当前上游版本建立对应关系。", False, None

        if len(direct_upstream_nodes) == 1:
            return (
                "pending",
                f'上游节点"{direct_upstream_nodes[0]["title"]}"已就绪，当前节点待执行。',
                False,
                None,
            )
        return (
            "pending",
            "上游节点已就绪，当前节点待执行。",
            False,
            None,
        )

    @staticmethod
    def _find_stale_upstream_title(
        *,
        active_version,
        expected_dependency_versions: dict[str, str],
        workflow_upstream_nodes: list[dict[str, Any]],
    ) -> str | None:
        dependency_version_ids = dict(active_version.dependency_version_ids)
        for upstream_node in reversed(workflow_upstream_nodes):
            node_id = upstream_node["node_id"]
            expected_version_id = expected_dependency_versions.get(node_id)
            current_version_id = dependency_version_ids.get(node_id)
            if expected_version_id != current_version_id:
                node_title = upstream_node.get("title")
                return str(node_title) if node_title else node_id
        return None

    @staticmethod
    def _get_completed_status(*, node_type: str, base_status: str) -> str:
        completed_status_by_node_type = {
            "user_input": "ready",
            SCRIPT_STORYBOARD_NODE_TYPE: "ready",
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

    @staticmethod
    def _split_node_id(node_id: str) -> tuple[str, str]:
        split_index = node_id.index(":")
        return node_id[:split_index], node_id[split_index + 1 :]

    @staticmethod
    def _resolve_version_source_node_id(bundle, *, node_type: str, node_key: str) -> str:
        node_spec = get_node_spec(bundle, node_type, node_key)
        return str(node_spec.get("version_source_node_id") or node_spec["node_id"])

    # ------------------------------------------------------------------
    # 辅助：从云端行构建运行记录
    # ------------------------------------------------------------------

    @staticmethod
    def _build_run_record_from_row(row: dict[str, Any]) -> SproutRunRecord:
        shot_ids = row.get("shot_ids")
        if not isinstance(shot_ids, list):
            shot_ids = []
        return SproutRunRecord(
            run_id=str(row.get("run_id") or "").strip(),
            project_id=str(row.get("project_id") or "").strip(),
            node_type=str(row.get("node_type") or "").strip(),
            node_key=str(row.get("node_key") or "").strip(),
            log_path=str(row.get("log_object_path") or "").strip(),
            status=str(row.get("status") or "running").strip(),
            created_at=str(row.get("created_at") or "").strip(),
            updated_at=str(row.get("updated_at") or "").strip(),
            source_version_id=row.get("source_version_id"),
            result_version_id=row.get("result_version_id"),
            shot_ids=[str(item) for item in shot_ids],
            error_message=row.get("error_message"),
        )

    # ------------------------------------------------------------------
    # 云端 Store 访问器
    # ------------------------------------------------------------------

    def _get_cloud_project_store(self) -> SproutCloudProjectStore:
        if self.cloud_project_store is None:
            self.cloud_project_store = SproutCloudProjectStore()
        return self.cloud_project_store

    def _get_cloud_version_store(self) -> SproutCloudVersionStore:
        if self.cloud_version_store is None:
            self.cloud_version_store = SproutCloudVersionStore()
        return self.cloud_version_store

    def _get_cloud_run_store(self) -> SproutCloudRunStore:
        if self.cloud_run_store is None:
            self.cloud_run_store = SproutCloudRunStore()
        return self.cloud_run_store
