"""Sprout 节点执行服务（云端版本）。"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..core.final_output import find_final_video_asset
from ..core.models import SproutAsset, SproutProjectBundle, SproutTopicInput
from ..core.orchestration import SproutWorkflow
from ..core.storage import SproutProjectStore
from .cloud_asset_store import SproutCloudAssetStore
from .cloud_project_store import SproutCloudProjectStore
from .cloud_run_store import SproutCloudRunStore
from .cloud_version_store import SproutCloudVersionStore
from .types import SproutNodeVersionRecord, SproutRunRecord, build_runtime_id, utc_now_isoformat
from .workflow_nodes import build_node_id, get_upstream_node_ids


@dataclass
class SproutWorkflowService:
    """负责执行一期后端可控节点（全云端，无本地文件系统依赖）。"""

    cloud_project_store: SproutCloudProjectStore | None = None
    cloud_version_store: SproutCloudVersionStore | None = None
    cloud_run_store: SproutCloudRunStore | None = None
    cloud_asset_store: SproutCloudAssetStore | None = None
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
        normalized_node_type = self._normalize_node_type(node_type)

        # ── 1. 从云端获取项目信息 ──
        project_row = self._get_cloud_project_store().get_project_row(project_id)
        if not isinstance(project_row, dict):
            raise KeyError(f"未找到项目：{project_id}")
        project_name = str(project_row.get("project_name") or "").strip()

        # ── 2. 下载最新 bundle 快照 ──
        canonical_payload = self._get_cloud_project_store().download_latest_bundle_snapshot(project_id)
        if not isinstance(canonical_payload, dict):
            raise ValueError(f"项目 {project_id} 尚无 bundle 快照。")
        canonical_bundle = SproutProjectBundle.from_dict(canonical_payload)

        # ── 3. 读取版本列表与激活状态 ──
        existing_versions = self._get_cloud_version_store().list_project_versions(project_id)
        active_state: dict[str, Any] = self._get_cloud_project_store().get_active_state(project_id)

        # ── 4. 确定来源版本 ──
        upstream_node_ids = get_upstream_node_ids(canonical_bundle, normalized_node_type, node_key)
        effective_source_version_id = (
            source_version_id or self._read_active_bundle_version_id(active_state)
            if upstream_node_ids
            else None
        )

        # ── 5. 加载工作 bundle（按需从指定版本快照还原）──
        if effective_source_version_id:
            bundle = self._load_bundle_for_version(effective_source_version_id, project_id)
        else:
            bundle = canonical_bundle

        # ── 6. 解析依赖版本 ──
        dependency_version_ids = self._resolve_dependency_version_ids(
            bundle=bundle,
            active_state=active_state,
            project_id=project_id,
            node_type=normalized_node_type,
            node_key=node_key,
            source_version_id=effective_source_version_id,
        )

        # ── 7. 构建运行记录（内存中）──
        run_id = build_runtime_id("run")
        run_record = SproutRunRecord(
            run_id=run_id,
            project_id=project_id,
            node_type=normalized_node_type,
            node_key=node_key,
            log_path="",
            status="running",
            source_version_id=effective_source_version_id,
            shot_ids=[node_key] if normalized_node_type in {"prepare_shot", "generate_shot"} else [],
        )
        log_messages: list[str] = []

        # 先写一次运行中状态
        self._get_cloud_run_store().upsert_run_record(run_record)

        workflow = SproutWorkflow()
        version_notes = [f"force={force}"]

        try:
            log_messages.append(f"执行节点类型：{normalized_node_type}，节点键：{node_key}。")
            if effective_source_version_id:
                log_messages.append(f"使用来源版本：{effective_source_version_id}。")

            # ── 8. 在临时目录中执行工作流节点 ──
            with tempfile.TemporaryDirectory(prefix="sprout_run_") as tmp_root:
                if normalized_node_type == "user_input":
                    bundle, input_mode = self._plan_from_user_input(
                        workflow=workflow,
                        current_bundle=bundle,
                        output_root=tmp_root,
                        project_name=project_name or canonical_bundle.project_name,
                        log_messages=log_messages,
                        user_input_payload=user_input_payload,
                    )
                    version_notes.append(f"input_mode={input_mode}")
                elif normalized_node_type == "characters":
                    workflow.build_characters(
                        project_bundle=bundle,
                        output_root=tmp_root,
                        extra_reference_count=extra_reference_count,
                        skip_existing=not force,
                    )
                elif normalized_node_type == "prepare_shot":
                    self._validate_shot_node_key(node_key)
                    workflow.prepare_shots(
                        project_bundle=bundle,
                        output_root=tmp_root,
                        shot_ids=[node_key],
                    )
                elif normalized_node_type == "generate_shot":
                    self._validate_shot_node_key(node_key)
                    workflow.generate_shots(
                        project_bundle=bundle,
                        output_root=tmp_root,
                        shot_ids=[node_key],
                        skip_existing=not force,
                    )
                elif normalized_node_type == "build_cards":
                    workflow.build_workflow_cards(
                        project_bundle=bundle,
                        output_root=tmp_root,
                    )
                elif normalized_node_type == "export":
                    workflow.export_bundle(
                        project_bundle=bundle,
                        output_root=tmp_root,
                    )
                elif normalized_node_type == "final_output":
                    workflow.build_final_video(
                        project_bundle=bundle,
                        output_root=tmp_root,
                    )
                    self._append_final_output_report_log(
                        log_messages=log_messages,
                        project_bundle=bundle,
                    )
                else:
                    raise ValueError(f"暂不支持的节点类型：{node_type}")

                # ── 9. 将 bundle 保存到临时目录（用于后续上传） ──
                self._get_project_store().save_bundle(
                    bundle,
                    output_root=tmp_root,
                )

                # ── 10. 上传产物资产到云端 ──
                uploaded_asset_ids = self._upload_new_assets(
                    project_bundle=bundle,
                    project_id=project_id,
                    output_root=tmp_root,
                )

            # ── 11. 保存 bundle 快照到云端 ──
            version_id = build_runtime_id("ver")
            snapshot_row = self._get_cloud_project_store().save_bundle_snapshot(
                project_id=project_id,
                project_bundle=bundle,
                snapshot_id=build_runtime_id("snapshot_bundle"),
                snapshot_type="bundle",
                source_version_id=effective_source_version_id,
            )
            snapshot_id = str(snapshot_row.get("snapshot_id") or "").strip()

            # ── 12. 创建版本记录 ──
            version_record = SproutNodeVersionRecord(
                version_id=version_id,
                project_id=project_id,
                node_type=normalized_node_type,
                node_key=node_key,
                bundle_snapshot_path="",
                source_version_id=effective_source_version_id,
                status="ready",
                run_id=run_record.run_id,
                asset_ids=uploaded_asset_ids,
                shot_ids=[node_key] if normalized_node_type in {"prepare_shot", "generate_shot"} else [],
                dependency_version_ids=dependency_version_ids,
                notes=version_notes,
            )
            self._get_cloud_version_store().upsert_version_record(
                version_record,
                snapshot_id=snapshot_id,
            )

            # ── 13. 更新激活状态 ──
            node_id = build_node_id(normalized_node_type, node_key)
            selected_versions = active_state.get("selected_versions")
            if not isinstance(selected_versions, dict):
                selected_versions = {}
            selected_versions[node_id] = version_id
            active_state["selected_versions"] = selected_versions
            active_state["active_bundle_version_id"] = version_id
            active_state["active_bundle_snapshot_id"] = snapshot_id
            self._get_cloud_project_store().update_active_state(project_id, active_state)

            # ── 14. 完成运行记录 ──
            run_record.status = "success"
            run_record.result_version_id = version_id
            run_record.updated_at = utc_now_isoformat()
            self._get_cloud_run_store().upsert_run_record(run_record)

            # ── 15. 上传运行日志 ──
            if log_messages:
                self._get_cloud_run_store().save_run_log(
                    project_id=project_id,
                    run_record=run_record,
                    log_text="\n".join(log_messages),
                )

            return {
                "run": run_record.to_dict(),
                "version": version_record.to_dict(),
                "active_state": active_state,
            }

        except Exception as exc:
            run_record.status = "failed"
            run_record.error_message = str(exc)
            run_record.updated_at = utc_now_isoformat()
            self._get_cloud_run_store().upsert_run_record(run_record)
            if log_messages:
                log_messages.append(f"执行失败：{exc}")
                try:
                    self._get_cloud_run_store().save_run_log(
                        project_id=project_id,
                        run_record=run_record,
                        log_text="\n".join(log_messages),
                    )
                except Exception:
                    pass
            raise

    # ────────────────────────────────────────────────────
    # 云端版本加载
    # ────────────────────────────────────────────────────

    def _load_bundle_for_version(self, version_id: str, project_id: str) -> SproutProjectBundle:
        """从云端版本行中获取 snapshot_id，下载快照并还原为 bundle。"""

        version_row = self._get_cloud_version_store().get_version_row(version_id)
        if not isinstance(version_row, dict):
            raise KeyError(f"未找到版本：{version_id}")
        snapshot_id = str(version_row.get("snapshot_id") or "").strip()
        if not snapshot_id:
            raise ValueError(f"版本 {version_id} 缺少 snapshot_id。")
        payload = self._get_cloud_project_store().download_snapshot(snapshot_id, project_id)
        return SproutProjectBundle.from_dict(payload)

    # ────────────────────────────────────────────────────
    # 依赖版本解析
    # ────────────────────────────────────────────────────

    def _resolve_dependency_version_ids(
        self,
        *,
        bundle,
        active_state: dict[str, object],
        project_id: str,
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

        # 回退：从来源版本记录中提取依赖
        source_version_row = self._get_cloud_version_store().get_version_row(source_version_id)
        if not isinstance(source_version_row, dict):
            return {}
        source_version = self._get_cloud_version_store().build_version_record_from_row(source_version_row)
        dependency_version_ids = {
            dependency_node_id: dependency_version_id
            for dependency_node_id, dependency_version_id in source_version.dependency_version_ids.items()
            if dependency_node_id in upstream_node_ids
        }
        source_node_id = build_node_id(source_version.node_type, source_version.node_key)
        if source_node_id in upstream_node_ids:
            dependency_version_ids[source_node_id] = source_version.version_id
        return dependency_version_ids

    # ────────────────────────────────────────────────────
    # 资产上传
    # ────────────────────────────────────────────────────

    def _upload_new_assets(
        self,
        *,
        project_bundle: SproutProjectBundle,
        project_id: str,
        output_root: str,
    ) -> list[str]:
        """扫描 bundle 中有本地路径的资产，上传到云端。"""

        uploaded_asset_ids: list[str] = []
        all_assets = list(project_bundle.assets)
        for shot in project_bundle.shots:
            all_assets.extend(shot.output_assets)
        for character in project_bundle.characters:
            all_assets.extend(character.reference_assets)

        for asset in all_assets:
            if not asset.path:
                continue
            local_path = Path(asset.path)
            if not local_path.is_absolute():
                local_path = Path(output_root) / local_path
            if not local_path.is_file():
                continue

            shot_id = self._infer_shot_id_for_asset(asset, project_bundle)
            character_id = self._infer_character_id_for_asset(asset, project_bundle)
            try:
                self._get_cloud_asset_store().save_asset_file(
                    asset,
                    project_id=project_id,
                    file_path=local_path,
                    shot_id=shot_id,
                    character_id=character_id,
                )
                uploaded_asset_ids.append(asset.asset_id)
            except Exception:
                pass
        return uploaded_asset_ids

    @staticmethod
    def _infer_shot_id_for_asset(asset: SproutAsset, bundle: SproutProjectBundle) -> str | None:
        for shot in bundle.shots:
            for output_asset in shot.output_assets:
                if output_asset.asset_id == asset.asset_id:
                    return shot.shot_id
        return None

    @staticmethod
    def _infer_character_id_for_asset(asset: SproutAsset, bundle: SproutProjectBundle) -> str | None:
        for character in bundle.characters:
            for ref_asset in character.reference_assets:
                if ref_asset.asset_id == asset.asset_id:
                    return character.character_id
        return None

    # ────────────────────────────────────────────────────
    # 最终成片日志
    # ────────────────────────────────────────────────────

    def _append_final_output_report_log(
        self,
        *,
        log_messages: list[str],
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

        log_messages.append("\n".join(summary_lines))

    # ────────────────────────────────────────────────────
    # 用户输入节点
    # ────────────────────────────────────────────────────

    def _plan_from_user_input(
        self,
        *,
        workflow: SproutWorkflow,
        current_bundle,
        output_root: str,
        project_name: str,
        log_messages: list[str],
        user_input_payload: dict[str, object] | None,
    ) -> tuple[object, str]:
        topic_input = self._build_topic_input(current_bundle, user_input_payload)
        storyboard_text = self._read_storyboard_text(current_bundle, user_input_payload)
        if not topic_input.topic and not storyboard_text:
            raise ValueError("请先填写题材，或提供已有分镜内容。")

        input_mode = "storyboard" if storyboard_text else "topic"
        log_messages.append(f"用户输入模式：{'已有分镜整理' if input_mode == 'storyboard' else '题材规划'}。")
        log_messages.append(
            f"题材：{topic_input.topic or '未填写'}；"
            f"镜头数：{topic_input.shot_count}；"
            f"总时长：{topic_input.duration_seconds} 秒。"
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

    # ────────────────────────────────────────────────────
    # 静态辅助方法
    # ────────────────────────────────────────────────────

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

    # ────────────────────────────────────────────────────
    # 懒初始化 store 访问器
    # ────────────────────────────────────────────────────

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

    def _get_cloud_asset_store(self) -> SproutCloudAssetStore:
        if self.cloud_asset_store is None:
            self.cloud_asset_store = SproutCloudAssetStore()
        return self.cloud_asset_store

    def _get_project_store(self) -> SproutProjectStore:
        if self.project_store is None:
            self.project_store = SproutProjectStore()
        return self.project_store
