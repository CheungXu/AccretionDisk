"""Sprout 节点执行服务。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..core.final_output import find_final_video_asset
from ..core.models import SproutTopicInput
from ..core.orchestration import SproutWorkflow
from ..core.storage import SproutProjectStore
from .registry import SproutProjectRegistry
from .runtime import SproutRunStore, SproutVersionStore
from .workflow_nodes import build_node_id, get_upstream_node_ids


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
        user_input_payload: dict[str, object] | None = None,
    ) -> dict[str, object]:
        record = self._get_registry().get_project(project_id)
        normalized_node_type = self._normalize_node_type(node_type)
        canonical_bundle = self._get_project_store().load_bundle(record.bundle_path)
        version_store = self._get_version_store()
        existing_versions = version_store.list_versions(record.canonical_root)
        if existing_versions:
            active_state = version_store.get_active_state(record.canonical_root)
        else:
            _, active_state = version_store.bootstrap_versions_from_project_files(
                project_root=record.canonical_root,
                project_bundle=canonical_bundle,
                project_id=project_id,
                bundle_path=record.bundle_path,
            )
        upstream_node_ids = get_upstream_node_ids(canonical_bundle, normalized_node_type, node_key)
        effective_source_version_id = (
            source_version_id or self._read_active_bundle_version_id(active_state)
            if upstream_node_ids
            else None
        )
        bundle = (
            version_store.load_bundle_for_version(record.canonical_root, effective_source_version_id)
            if effective_source_version_id
            else canonical_bundle
        )
        dependency_version_ids = self._resolve_dependency_version_ids(
            bundle=bundle,
            active_state=active_state,
            project_root=record.canonical_root,
            node_type=normalized_node_type,
            node_key=node_key,
            source_version_id=effective_source_version_id,
        )
        run_record = self._get_run_store().start_run(
            project_root=record.canonical_root,
            project_id=project_id,
            node_type=normalized_node_type,
            node_key=node_key,
            source_version_id=effective_source_version_id,
            shot_ids=[node_key] if normalized_node_type in {"prepare_shot", "generate_shot"} else None,
        )
        workflow = SproutWorkflow()
        version_notes = [f"force={force}"]
        try:
            self._get_run_store().append_log(
                project_root=record.canonical_root,
                run_record=run_record,
                message=f"执行节点类型：{normalized_node_type}，节点键：{node_key}。",
            )
            if effective_source_version_id:
                self._get_run_store().append_log(
                    project_root=record.canonical_root,
                    run_record=run_record,
                    message=f"使用来源版本：{effective_source_version_id}。",
                )

            if normalized_node_type == "user_input":
                bundle, input_mode = self._plan_from_user_input(
                    workflow=workflow,
                    current_bundle=bundle,
                    output_root=record.canonical_root,
                    project_name=canonical_bundle.project_name,
                    run_record=run_record,
                    project_root=record.canonical_root,
                    user_input_payload=user_input_payload,
                )
                version_notes.append(f"input_mode={input_mode}")
            elif normalized_node_type == "characters":
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
            elif normalized_node_type == "final_output":
                workflow.build_final_video(
                    project_bundle=bundle,
                    output_root=record.canonical_root,
                )
                self._append_final_output_report_log(
                    project_root=record.canonical_root,
                    run_record=run_record,
                    project_bundle=bundle,
                )
            else:
                raise ValueError(f"暂不支持的节点类型：{node_type}")

            version_record = version_store.create_version(
                project_root=record.canonical_root,
                project_bundle=bundle,
                project_id=project_id,
                node_type=normalized_node_type,
                node_key=node_key,
                source_version_id=effective_source_version_id,
                run_id=run_record.run_id,
                shot_ids=[node_key] if normalized_node_type in {"prepare_shot", "generate_shot"} else None,
                dependency_version_ids=dependency_version_ids,
                notes=version_notes,
            )
            active_state = version_store.activate_version(
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

    def _resolve_dependency_version_ids(
        self,
        *,
        bundle,
        active_state: dict[str, object],
        project_root: str,
        node_type: str,
        node_key: str,
        source_version_id: str | None,
    ) -> dict[str, str]:
        upstream_node_ids = set(get_upstream_node_ids(bundle, node_type, node_key))
        if not upstream_node_ids or not source_version_id:
            raw_selected_versions = active_state.get("selected_versions", {})
            if not isinstance(raw_selected_versions, dict):
                return {}
            return {
                str(dependency_node_id): str(dependency_version_id)
                for dependency_node_id, dependency_version_id in raw_selected_versions.items()
                if str(dependency_node_id) in upstream_node_ids and str(dependency_version_id).strip()
            }

        raw_selected_versions = active_state.get("selected_versions", {})
        if isinstance(raw_selected_versions, dict):
            selected_dependency_versions = {
                str(dependency_node_id): str(dependency_version_id)
                for dependency_node_id, dependency_version_id in raw_selected_versions.items()
                if str(dependency_node_id) in upstream_node_ids and str(dependency_version_id).strip()
            }
            if selected_dependency_versions:
                return selected_dependency_versions

        source_version = self._get_version_store().get_version(project_root, source_version_id)
        dependency_version_ids = {
            dependency_node_id: dependency_version_id
            for dependency_node_id, dependency_version_id in source_version.dependency_version_ids.items()
            if dependency_node_id in upstream_node_ids
        }
        source_node_id = build_node_id(source_version.node_type, source_version.node_key)
        if source_node_id in upstream_node_ids:
            dependency_version_ids[source_node_id] = source_version.version_id
        return dependency_version_ids

    def _append_final_output_report_log(
        self,
        *,
        project_root: str,
        run_record,
        project_bundle,
    ) -> None:
        final_asset = find_final_video_asset(project_bundle)
        resolution_report = (
            dict(final_asset.metadata).get("resolution_report")
            if final_asset is not None and isinstance(final_asset.metadata, dict)
            else None
        )
        if not isinstance(resolution_report, dict):
            return

        target_render_size = resolution_report.get("target_render_size") or {}
        target_label = target_render_size.get("label") or "未知"
        summary_lines = [
            "最终成片分辨率统计：",
            f"- 片段总数：{resolution_report.get('segment_count', 0)}",
            f"- 目标输出分辨率：{target_label}",
            f"- 需黑边适配片段数：{resolution_report.get('padded_segment_count', 0)}",
            f"- 需放大片段数：{resolution_report.get('upscale_segment_count', 0)}",
        ]

        resolution_summary = resolution_report.get("resolution_summary") or []
        if resolution_summary:
            summary_lines.append(
                "- 分辨率分布：" + "；".join(
                    f"{item.get('label', '未知')} x {item.get('count', 0)}"
                    for item in resolution_summary
                    if isinstance(item, dict)
                )
            )

        warnings = resolution_report.get("warnings") or []
        if warnings:
            summary_lines.append(
                "- 合并策略说明：" + "；".join(str(item) for item in warnings if str(item).strip())
            )

        segments = resolution_report.get("segments") or []
        highlighted_segments = []
        for segment in segments:
            if not isinstance(segment, dict):
                continue
            if segment.get("needs_padding") or segment.get("scale_mode") != "native":
                highlighted_segments.append(
                    f"{segment.get('file_name')} -> {segment.get('resolution_label')} ({segment.get('scale_mode')})"
                )
        if highlighted_segments:
            summary_lines.append("- 重点适配片段：" + "；".join(highlighted_segments[:8]))

        segment_details = []
        for segment in segments:
            if not isinstance(segment, dict):
                continue
            segment_details.append(
                f"{segment.get('file_name')} -> {segment.get('resolution_label')}，"
                f"模式={segment.get('scale_mode')}，"
                f"黑边适配={'是' if segment.get('needs_padding') else '否'}"
            )
        if segment_details:
            summary_lines.append("- 片段明细：" + "；".join(segment_details))

        self._get_run_store().append_log(
            project_root=project_root,
            run_record=run_record,
            message="\n".join(summary_lines),
        )

    def _plan_from_user_input(
        self,
        *,
        workflow: SproutWorkflow,
        current_bundle,
        output_root: str,
        project_name: str,
        run_record,
        project_root: str,
        user_input_payload: dict[str, object] | None,
    ) -> tuple[object, str]:
        topic_input = self._build_topic_input(current_bundle, user_input_payload)
        storyboard_text = self._read_storyboard_text(current_bundle, user_input_payload)
        if not topic_input.topic and not storyboard_text:
            raise ValueError("请先填写题材，或提供已有分镜内容。")

        input_mode = "storyboard" if storyboard_text else "topic"
        self._get_run_store().append_log(
            project_root=project_root,
            run_record=run_record,
            message=f"用户输入模式：{'已有分镜整理' if input_mode == 'storyboard' else '题材规划'}。",
        )
        self._get_run_store().append_log(
            project_root=project_root,
            run_record=run_record,
            message=(
                f"题材：{topic_input.topic or '未填写'}；"
                f"镜头数：{topic_input.shot_count}；"
                f"总时长：{topic_input.duration_seconds} 秒。"
            ),
        )

        if storyboard_text:
            return (
                workflow.plan_from_storyboard(
                    storyboard_text=storyboard_text,
                    output_root=output_root,
                    topic_input=topic_input,
                    project_name=project_name,
                ),
                input_mode,
            )

        return (
            workflow.plan_from_topic(
                topic_input=topic_input,
                output_root=output_root,
                project_name=project_name,
            ),
            input_mode,
        )

    @staticmethod
    def _read_active_bundle_version_id(active_state: dict[str, object]) -> str | None:
        active_bundle_version_id = active_state.get("active_bundle_version_id")
        if active_bundle_version_id is None:
            return None
        normalized_value = str(active_bundle_version_id).strip()
        return normalized_value or None

    @staticmethod
    def _normalize_node_type(node_type: str) -> str:
        normalized_value = node_type.strip().lower()
        aliases = {
            "input": "user_input",
            "topic_input": "user_input",
            "build_characters": "characters",
            "prepare_shots": "prepare_shot",
            "generate_shots": "generate_shot",
            "build_cards": "build_cards",
            "final_video": "final_output",
        }
        return aliases.get(normalized_value, normalized_value)

    def _build_topic_input(self, bundle, payload: dict[str, object] | None) -> SproutTopicInput:
        payload = payload or {}
        current_input = bundle.topic_input
        topic = (
            self._normalize_optional_text(payload.get("topic")) or ""
            if "topic" in payload
            else current_input.topic
        )
        orientation = self._normalize_optional_text(payload.get("orientation"))
        return SproutTopicInput(
            topic=topic,
            duration_seconds=self._parse_positive_int(
                payload.get("duration_seconds"),
                default=current_input.duration_seconds,
                field_label="总时长",
            ),
            shot_count=self._parse_positive_int(
                payload.get("shot_count"),
                default=current_input.shot_count,
                field_label="镜头数",
            ),
            orientation=orientation or current_input.orientation or "9:16",
            visual_style=(
                self._normalize_optional_text(payload.get("visual_style"))
                if "visual_style" in payload
                else current_input.visual_style
            ),
            target_audience=(
                self._normalize_optional_text(payload.get("target_audience"))
                if "target_audience" in payload
                else current_input.target_audience
            ),
            notes=(
                self._normalize_optional_text(payload.get("notes"))
                if "notes" in payload
                else current_input.notes
            ),
        )

    def _read_storyboard_text(self, bundle, payload: dict[str, object] | None) -> str | None:
        payload = payload or {}
        if "source_storyboard" not in payload:
            return self._normalize_optional_text(bundle.source_storyboard)
        return self._normalize_optional_text(payload.get("source_storyboard"))

    @staticmethod
    def _parse_positive_int(value: Any, *, default: int, field_label: str) -> int:
        if value in {None, ""}:
            return max(int(default), 1)
        try:
            parsed_value = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field_label} 必须是整数。") from exc
        if parsed_value <= 0:
            raise ValueError(f"{field_label} 必须大于 0。")
        return parsed_value

    @staticmethod
    def _normalize_optional_text(value: Any) -> str | None:
        if value is None:
            return None
        normalized_value = str(value).strip()
        return normalized_value or None

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
