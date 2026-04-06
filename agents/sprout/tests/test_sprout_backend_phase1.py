"""Sprout 一期后端能力测试。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import quote

from agents.sprout import (
    SproutAsset,
    SproutExporter,
    SproutJimengPackager,
    SproutProjectBundle,
    SproutProjectStore,
    SproutRunStore,
    SproutTopicInput,
    SproutVersionStore,
)
from agents.sprout.core.video_merger import SproutVideoMerger
from agents.sprout.service import (
    SproutHttpApi,
    SproutMediaService,
    SproutProjectAdapter,
    SproutProjectRegistry,
    SproutProjectService,
    SproutWorkflowService,
)
from agents.sprout.service.http_server import _SproutApiHandler
from agents.sprout.tests.test_sprout_smoke import build_demo_bundle


def build_importable_project(root: Path) -> Path:
    bundle = build_demo_bundle(root)
    store = SproutProjectStore()
    store.save_bundle(bundle, output_root=root)

    packager = SproutJimengPackager()
    packager.build_cards(bundle)
    exporter = SproutExporter(jimeng_packager=packager)
    exporter.export_bundle(bundle, output_root=root)
    return root


def build_completed_project(root: Path) -> Path:
    bundle = build_demo_bundle(root)
    store = SproutProjectStore()

    shots_root = root / "shots"
    videos_root = root / "videos"
    shots_root.mkdir(parents=True, exist_ok=True)
    videos_root.mkdir(parents=True, exist_ok=True)

    for shot in bundle.shots:
        shot_root = shots_root / shot.shot_id
        shot_root.mkdir(parents=True, exist_ok=True)
        keyframe_path = shot_root / f"{shot.shot_id}_keyframe_01.jpg"
        video_path = videos_root / f"{shot.shot_id}_01.mp4"
        keyframe_path.write_text("keyframe", encoding="utf-8")
        video_path.write_text("video", encoding="utf-8")
        shot.keyframe_prompt = f"{shot.title} 首帧提示词"
        shot.video_prompt = f"{shot.title} 视频提示词"
        shot.status = "generated"
        shot.output_assets = [
            SproutAsset(
                asset_id=f"{shot.shot_id}_keyframe",
                asset_type="shot_keyframe",
                source="seed_image",
                path=str(keyframe_path),
            ),
            SproutAsset(
                asset_id=f"{shot.shot_id}_video_01",
                asset_type="shot_video",
                source="seed_video",
                path=str(video_path),
            ),
        ]
        for asset in shot.output_assets:
            bundle.register_asset(asset)

    packager = SproutJimengPackager()
    packager.build_cards(bundle)
    exporter = SproutExporter(jimeng_packager=packager)
    store.save_bundle(bundle, output_root=root)
    exporter.export_bundle(bundle, output_root=root)
    manifest_json = root / "manifest" / f"{bundle.project_name}_manifest.json"
    summary_md = root / "manifest" / f"{bundle.project_name}_summary.md"
    manifest_json.touch()
    summary_md.touch()
    return root


def build_planned_bundle(*, project_name: str, topic_input: SproutTopicInput) -> SproutProjectBundle:
    topic_text = topic_input.topic or "空项目规划"
    return SproutProjectBundle.from_planning_data(
        {
            "title": f"{topic_text}·测试方案",
            "core_hook": "测试冲突",
            "visual_style": topic_input.visual_style or "测试风格",
            "characters": [
                {
                    "name": "主角",
                    "role": "主角",
                    "summary": "用于测试用户输入节点",
                    "appearance_prompt": "测试主角形象",
                }
            ],
            "shots": [
                {
                    "shot_index": 1,
                    "title": "测试镜头",
                    "visual_description": "主角出场",
                    "dialogue": "测试台词",
                    "sound_effects": "测试音效",
                    "camera_language": "中景推进",
                    "emotion": "坚定",
                    "characters": ["主角"],
                }
            ],
        },
        topic_input=topic_input,
        project_name=project_name,
    )


class SproutBackendPhase1Test(unittest.TestCase):
    def _build_services(self, temp_root: Path):
        registry = SproutProjectRegistry(registry_root=temp_root / "registry")
        adapter = SproutProjectAdapter(managed_projects_root=temp_root / "managed_projects")
        version_store = SproutVersionStore()
        run_store = SproutRunStore()
        project_service = SproutProjectService(
            adapter=adapter,
            registry=registry,
            version_store=version_store,
            run_store=run_store,
        )
        workflow_service = SproutWorkflowService(
            registry=registry,
            version_store=version_store,
            run_store=run_store,
        )
        media_service = SproutMediaService(registry=registry)
        api = SproutHttpApi(
            project_service=project_service,
            workflow_service=workflow_service,
            media_service=media_service,
        )
        return project_service, workflow_service, api

    @staticmethod
    def _get_node(nodes: list[dict[str, object]], node_id: str) -> dict[str, object]:
        for node in nodes:
            if node["node_id"] == node_id:
                return node
        raise AssertionError(f"未找到节点：{node_id}")

    def test_import_project_registers_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            project_root = build_importable_project(temp_root / "demo_project")
            project_service, _, _ = self._build_services(temp_root)

            imported_project = project_service.import_project(project_root, import_mode="reference")
            listed_projects = project_service.list_projects()

            self.assertEqual(imported_project["project_name"], "测试项目")
            self.assertEqual(len(listed_projects), 1)
            self.assertEqual(listed_projects[0]["display_name"], "测试项目")
            self.assertEqual(listed_projects[0]["character_count"], 2)

    def test_import_empty_directory_initializes_placeholder_project(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            project_root = temp_root / "empty_project"
            project_root.mkdir(parents=True, exist_ok=True)
            project_service, _, _ = self._build_services(temp_root)

            imported_project = project_service.import_project(project_root, import_mode="reference")
            project_detail = project_service.get_project_detail(imported_project["project_id"])

            self.assertEqual(imported_project["health_status"], "draft")
            self.assertEqual([node["node_id"] for node in project_detail["nodes"]], ["user_input:project"])
            self.assertEqual(project_detail["nodes"][0]["status"], "pending")
            self.assertEqual(project_detail["bundle"]["topic_input"]["topic"], "")
            self.assertTrue((project_root / "script").exists())
            self.assertTrue((project_root / "input").exists())

    def test_run_prepare_shot_creates_version_and_log(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            project_root = build_importable_project(temp_root / "demo_project")
            project_service, workflow_service, _ = self._build_services(temp_root)

            imported_project = project_service.import_project(project_root, import_mode="reference")
            run_payload = workflow_service.run_node(
                project_id=imported_project["project_id"],
                node_type="prepare_shot",
                node_key="shot_001",
            )
            project_detail = project_service.get_project_detail(imported_project["project_id"])
            run_detail = project_service.get_run_detail(
                imported_project["project_id"],
                run_payload["run"]["run_id"],
            )

            self.assertEqual(run_payload["run"]["status"], "success")
            self.assertEqual(
                run_payload["active_state"]["active_bundle_version_id"],
                run_payload["version"]["version_id"],
            )
            self.assertTrue(project_detail["versions"])
            self.assertIn("开始执行节点", run_detail["log"])
            self.assertEqual(
                project_detail["bundle"]["shots"][0]["status"],
                "prompt_ready",
            )

    def test_run_user_input_replans_empty_project(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            project_root = temp_root / "empty_project"
            project_root.mkdir(parents=True, exist_ok=True)
            project_service, workflow_service, _ = self._build_services(temp_root)

            imported_project = project_service.import_project(project_root, import_mode="reference")
            project_id = imported_project["project_id"]

            def fake_plan_from_topic(self, topic_input, *, project_name=None):
                return build_planned_bundle(project_name=project_name or "empty_project", topic_input=topic_input)

            with patch(
                "agents.sprout.core.script_planner.SproutScriptPlanner.plan_from_topic",
                new=fake_plan_from_topic,
            ):
                run_payload = workflow_service.run_node(
                    project_id=project_id,
                    node_type="user_input",
                    user_input_payload={
                        "topic": "古风逆袭短剧",
                        "duration_seconds": 72,
                        "shot_count": 12,
                        "orientation": "9:16",
                        "visual_style": "国漫古风",
                        "target_audience": "短剧用户",
                        "notes": "需要强冲突",
                        "source_storyboard": "",
                    },
                )

            project_detail = project_service.get_project_detail(project_id)
            self.assertEqual(run_payload["run"]["status"], "success")
            self.assertEqual(
                self._get_node(project_detail["nodes"], "user_input:project")["status"],
                "ready",
            )
            self.assertEqual(
                self._get_node(project_detail["nodes"], "characters:project")["status"],
                "pending",
            )
            self.assertEqual(
                self._get_node(project_detail["nodes"], "prepare_shot:shot_001")["status"],
                "waiting",
            )
            self.assertEqual(project_detail["bundle"]["topic_input"]["topic"], "古风逆袭短剧")
            self.assertEqual(project_detail["bundle"]["project_name"], imported_project["project_name"])
            self.assertTrue((project_root / "script").exists())

    def test_http_api_exposes_import_run_and_media(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            project_root = build_importable_project(temp_root / "demo_project")
            _, _, api = self._build_services(temp_root)

            status_code, _, response_body = api.handle_request(
                method="POST",
                raw_path="/api/projects/import",
                body=json.dumps(
                    {
                        "project_root": str(project_root),
                        "import_mode": "reference",
                    },
                    ensure_ascii=False,
                ).encode("utf-8"),
            )
            imported_project = json.loads(response_body.decode("utf-8"))
            project_id = imported_project["project_id"]

            status_code, _, response_body = api.handle_request(
                method="POST",
                raw_path=f"/api/projects/{project_id}/nodes/run",
                body=json.dumps(
                    {
                        "node_type": "prepare_shot",
                        "node_key": "shot_001",
                    },
                    ensure_ascii=False,
                ).encode("utf-8"),
            )
            run_payload = json.loads(response_body.decode("utf-8"))

            status_code, _, response_body = api.handle_request(
                method="GET",
                raw_path=f"/api/projects/{project_id}/nodes/detail?node_type=prepare_shot&node_key=shot_001",
            )
            node_detail = json.loads(response_body.decode("utf-8"))

            status_code, _, response_body = api.handle_request(
                method="GET",
                raw_path=f"/api/projects/{project_id}/versions/{run_payload['version']['version_id']}",
            )
            version_detail = json.loads(response_body.decode("utf-8"))

            status_code, headers, media_body = api.handle_request(
                method="GET",
                raw_path=(
                    f"/api/projects/{project_id}/media?path="
                    f"{quote(str(project_root / 'characters' / 'shen.png'))}"
                ),
            )

            self.assertEqual(status_code, 200)
            self.assertEqual(run_payload["run"]["status"], "success")
            self.assertEqual(node_detail["node"]["node_type"], "prepare_shot")
            self.assertEqual(version_detail["version"]["version_id"], run_payload["version"]["version_id"])
            self.assertEqual(headers["Content-Type"], "image/png")
            self.assertEqual(media_body.decode("utf-8"), "shen")

    def test_http_api_exposes_directory_picker(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            _, _, api = self._build_services(temp_root)

            with patch(
                "agents.sprout.service.http_api.SproutDirectoryPicker.pick_directory",
                return_value={
                    "cancelled": False,
                    "project_root": str(temp_root / "selected_project"),
                    "is_empty": True,
                },
            ):
                status_code, _, response_body = api.handle_request(
                    method="POST",
                    raw_path="/api/projects/select-directory",
                    body=json.dumps({}, ensure_ascii=False).encode("utf-8"),
                )

            payload = json.loads(response_body.decode("utf-8"))
            self.assertEqual(status_code, 200)
            self.assertEqual(payload["project_root"], str(temp_root / "selected_project"))
            self.assertTrue(payload["is_empty"])

    def test_project_detail_status_tracks_version_chain_freshness(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            project_root = build_importable_project(temp_root / "demo_project")
            project_service, workflow_service, _ = self._build_services(temp_root)

            imported_project = project_service.import_project(project_root, import_mode="reference")
            project_id = imported_project["project_id"]
            initial_detail = project_service.get_project_detail(project_id)
            user_input_version_id = self._get_node(
                initial_detail["nodes"],
                "user_input:project",
            )["active_version_id"]
            self.assertIsNotNone(user_input_version_id)

            character_v1 = workflow_service.run_node(
                project_id=project_id,
                node_type="characters",
            )
            prepare_v1 = workflow_service.run_node(
                project_id=project_id,
                node_type="prepare_shot",
                node_key="shot_001",
            )

            def fake_generate_shots(self, *, project_bundle, output_root, **kwargs):
                shot = project_bundle.find_shot("shot_001")
                if shot is None:
                    raise AssertionError("未找到测试镜头 shot_001")
                video_root = Path(output_root) / "videos"
                video_root.mkdir(parents=True, exist_ok=True)
                video_path = video_root / "shot_001_test.mp4"
                video_path.write_text("video", encoding="utf-8")
                shot.status = "generated"
                shot.output_assets = [
                    SproutAsset(
                        asset_id="shot_001_video_test",
                        asset_type="shot_video",
                        source="seed_video",
                        path=str(video_path),
                    )
                ]
                for asset in shot.output_assets:
                    project_bundle.register_asset(asset)
                self._get_project_store().save_bundle(project_bundle, output_root=output_root)
                return project_bundle

            with patch("agents.sprout.core.workflow.SproutWorkflow.generate_shots", new=fake_generate_shots):
                generate_v1 = workflow_service.run_node(
                    project_id=project_id,
                    node_type="generate_shot",
                    node_key="shot_001",
                )

            self.assertEqual(
                character_v1["version"]["dependency_version_ids"],
                {
                    "user_input:project": user_input_version_id,
                },
            )
            self.assertEqual(
                prepare_v1["version"]["source_version_id"],
                character_v1["version"]["version_id"],
            )
            self.assertEqual(
                prepare_v1["version"]["dependency_version_ids"],
                {
                    "user_input:project": user_input_version_id,
                    "characters:project": character_v1["version"]["version_id"],
                },
            )
            self.assertEqual(
                generate_v1["version"]["source_version_id"],
                prepare_v1["version"]["version_id"],
            )
            self.assertEqual(
                generate_v1["version"]["dependency_version_ids"],
                {
                    "user_input:project": user_input_version_id,
                    "characters:project": character_v1["version"]["version_id"],
                    "prepare_shot:shot_001": prepare_v1["version"]["version_id"],
                },
            )

            project_detail = project_service.get_project_detail(project_id)
            self.assertEqual(
                self._get_node(project_detail["nodes"], "user_input:project")["status"],
                "ready",
            )
            self.assertEqual(
                self._get_node(project_detail["nodes"], "characters:project")["status"],
                "generated",
            )
            self.assertEqual(
                self._get_node(project_detail["nodes"], "prepare_shot:shot_001")["status"],
                "prompt_ready",
            )
            self.assertEqual(
                self._get_node(project_detail["nodes"], "generate_shot:shot_001")["status"],
                "generated",
            )

            character_v2 = workflow_service.run_node(
                project_id=project_id,
                node_type="characters",
            )
            project_detail = project_service.get_project_detail(project_id)
            self.assertEqual(
                self._get_node(project_detail["nodes"], "prepare_shot:shot_001")["status"],
                "pending",
            )
            self.assertEqual(
                self._get_node(project_detail["nodes"], "generate_shot:shot_001")["status"],
                "waiting",
            )

            prepare_v2 = workflow_service.run_node(
                project_id=project_id,
                node_type="prepare_shot",
                node_key="shot_001",
            )
            self.assertEqual(
                prepare_v2["version"]["dependency_version_ids"],
                {
                    "user_input:project": user_input_version_id,
                    "characters:project": character_v2["version"]["version_id"],
                },
            )

            project_detail = project_service.get_project_detail(project_id)
            self.assertEqual(
                self._get_node(project_detail["nodes"], "prepare_shot:shot_001")["status"],
                "prompt_ready",
            )
            self.assertEqual(
                self._get_node(project_detail["nodes"], "generate_shot:shot_001")["status"],
                "pending",
            )

            node_detail = project_service.get_node_detail(
                project_id,
                node_type="generate_shot",
                node_key="shot_001",
            )
            self.assertEqual(node_detail["node"]["status"], "pending")

    def test_user_input_version_marks_downstream_nodes_pending(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            project_root = build_completed_project(temp_root / "completed_project")
            project_service, workflow_service, _ = self._build_services(temp_root)

            imported_project = project_service.import_project(project_root, import_mode="reference")
            project_id = imported_project["project_id"]
            initial_detail = project_service.get_project_detail(project_id)
            self.assertEqual(
                self._get_node(initial_detail["nodes"], "generate_shot:shot_001")["status"],
                "generated",
            )

            def fake_plan_from_topic(self, topic_input, *, project_name=None):
                return build_planned_bundle(project_name=project_name or "completed_project", topic_input=topic_input)

            with patch(
                "agents.sprout.core.script_planner.SproutScriptPlanner.plan_from_topic",
                new=fake_plan_from_topic,
            ):
                run_payload = workflow_service.run_node(
                    project_id=project_id,
                    node_type="user_input",
                    user_input_payload={
                        "topic": "重生复仇短剧",
                        "duration_seconds": 60,
                        "shot_count": 10,
                        "orientation": "9:16",
                        "visual_style": "国漫厚涂",
                        "target_audience": "短剧用户",
                        "notes": "强化冲突",
                        "source_storyboard": "",
                    },
                )

            project_detail = project_service.get_project_detail(project_id)
            self.assertEqual(
                self._get_node(project_detail["nodes"], "user_input:project")["active_version_id"],
                run_payload["version"]["version_id"],
            )
            self.assertEqual(
                self._get_node(project_detail["nodes"], "characters:project")["status"],
                "pending",
            )
            self.assertEqual(
                self._get_node(project_detail["nodes"], "prepare_shot:shot_001")["status"],
                "waiting",
            )
            self.assertEqual(
                self._get_node(project_detail["nodes"], "generate_shot:shot_001")["status"],
                "waiting",
            )

    def test_project_detail_bootstraps_versions_from_filesystem(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            project_root = build_completed_project(temp_root / "completed_project")
            project_service, _, _ = self._build_services(temp_root)

            imported_project = project_service.import_project(project_root, import_mode="reference")
            project_detail = project_service.get_project_detail(imported_project["project_id"])

            self.assertTrue(project_detail["versions"])
            self.assertEqual(
                self._get_node(project_detail["nodes"], "user_input:project")["status"],
                "ready",
            )
            self.assertEqual(
                self._get_node(project_detail["nodes"], "characters:project")["status"],
                "generated",
            )
            self.assertEqual(
                self._get_node(project_detail["nodes"], "prepare_shot:shot_001")["status"],
                "prompt_ready",
            )
            self.assertEqual(
                self._get_node(project_detail["nodes"], "generate_shot:shot_001")["status"],
                "generated",
            )
            self.assertEqual(
                self._get_node(project_detail["nodes"], "build_cards:project")["status"],
                "ready",
            )
            self.assertEqual(
                self._get_node(project_detail["nodes"], "export:project")["status"],
                "ready",
            )
            self.assertTrue(project_detail["active_state"]["selected_versions"])

    def test_filesystem_versions_keep_downstream_waiting_when_upstream_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            project_root = build_completed_project(temp_root / "completed_project")
            project_service, _, _ = self._build_services(temp_root)

            imported_project = project_service.import_project(project_root, import_mode="reference")

            keyframe_asset = project_root / "shots" / "shot_001" / "shot_001_keyframe_01.jpg"
            video_asset = project_root / "videos" / "shot_001_01.mp4"
            keyframe_asset.unlink()
            video_asset.unlink()

            project_detail = project_service.get_project_detail(imported_project["project_id"])

            self.assertEqual(
                self._get_node(project_detail["nodes"], "characters:project")["status"],
                "generated",
            )
            self.assertEqual(
                self._get_node(project_detail["nodes"], "prepare_shot:shot_001")["status"],
                "prompt_ready",
            )
            self.assertEqual(
                self._get_node(project_detail["nodes"], "generate_shot:shot_001")["status"],
                "pending",
            )
            self.assertEqual(
                self._get_node(project_detail["nodes"], "build_cards:project")["status"],
                "waiting",
            )

    def test_run_final_output_creates_final_video(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            project_root = build_completed_project(temp_root / "completed_project")
            project_service, workflow_service, _ = self._build_services(temp_root)

            imported_project = project_service.import_project(project_root, import_mode="reference")
            project_id = imported_project["project_id"]

            project_detail = project_service.get_project_detail(project_id)
            self.assertEqual(
                self._get_node(project_detail["nodes"], "final_output:project")["status"],
                "pending",
            )

            fake_resolution_report = {
                "strategy": "先统计片段分辨率，再按无需放大低分辨率片段优先的原则选择输出分辨率。",
                "segment_count": 1,
                "target_render_size": {"width": 720, "height": 1280, "label": "720 x 1280"},
                "resolution_summary": [{"label": "720 x 1280", "count": 1}],
                "orientation_summary": {"portrait": 1},
                "upscale_segment_count": 0,
                "padded_segment_count": 0,
                "segments": [
                    {
                        "index": 1,
                        "shot_id": "shot_001",
                        "file_name": "shot_001_01.mp4",
                        "duration_seconds": 6.0,
                        "display_width": 720,
                        "display_height": 1280,
                        "resolution_label": "720 x 1280",
                        "orientation": "portrait",
                        "scale_mode": "native",
                        "needs_padding": False,
                    }
                ],
                "warnings": ["目标输出分辨率已优先选择无需放大低分辨率片段的方案。"],
            }

            def fake_merge(self, input_paths, output_path, *, merge_plan=None):
                output_path = Path(output_path)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text("merged-video", encoding="utf-8")
                return output_path

            def fake_build_merge_plan(self, input_paths):
                return fake_resolution_report

            with patch(
                "agents.sprout.core.video_merger.SproutVideoMerger.merge_videos",
                new=fake_merge,
            ), patch(
                "agents.sprout.core.video_merger.SproutVideoMerger.build_merge_plan",
                new=fake_build_merge_plan,
            ):
                run_payload = workflow_service.run_node(
                    project_id=project_id,
                    node_type="final_output",
                )

            self.assertEqual(run_payload["run"]["status"], "success")
            project_detail = project_service.get_project_detail(project_id)
            final_output_node = self._get_node(project_detail["nodes"], "final_output:project")
            self.assertEqual(final_output_node["status"], "ready")
            self.assertIsNotNone(final_output_node["active_version_id"])

            node_detail = project_service.get_node_detail(
                project_id,
                node_type="final_output",
                node_key="project",
            )
            self.assertEqual(node_detail["node"]["status"], "ready")
            self.assertEqual(
                node_detail["node"]["payload"]["asset"]["asset_type"],
                "final_video",
            )
            self.assertEqual(
                node_detail["node"]["payload"]["resolution_report"]["target_render_size"]["label"],
                "720 x 1280",
            )
            self.assertTrue(Path(node_detail["node"]["payload"]["asset"]["path"]).exists())

            run_detail = project_service.get_run_detail(
                project_id,
                run_payload["run"]["run_id"],
            )
            self.assertIn("最终成片分辨率统计", run_detail["log"])
            self.assertIn("目标输出分辨率：720 x 1280", run_detail["log"])

    def test_video_merger_prefers_non_upscale_target_resolution(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            input_paths = []
            for file_name in ("shot_001_01.mp4", "shot_002_01.mp4", "shot_004_01.mp4"):
                path = temp_root / file_name
                path.write_text("video", encoding="utf-8")
                input_paths.append(path)

            merger = SproutVideoMerger()

            fake_profiles = [
                {
                    "input_path": str(input_paths[0]),
                    "file_name": input_paths[0].name,
                    "natural_width": 720,
                    "natural_height": 1280,
                    "display_width": 720,
                    "display_height": 1280,
                    "duration_seconds": 6.0,
                    "orientation": "portrait",
                },
                {
                    "input_path": str(input_paths[1]),
                    "file_name": input_paths[1].name,
                    "natural_width": 720,
                    "natural_height": 1280,
                    "display_width": 720,
                    "display_height": 1280,
                    "duration_seconds": 6.0,
                    "orientation": "portrait",
                },
                {
                    "input_path": str(input_paths[2]),
                    "file_name": input_paths[2].name,
                    "natural_width": 1280,
                    "natural_height": 720,
                    "display_width": 1280,
                    "display_height": 720,
                    "duration_seconds": 6.0,
                    "orientation": "landscape",
                },
            ]

            with patch.object(merger, "_inspect_video_profiles", return_value=fake_profiles):
                report = merger.build_merge_plan(input_paths)

            self.assertEqual(report["target_render_size"]["label"], "720 x 1280")
            self.assertEqual(report["upscale_segment_count"], 0)
            self.assertEqual(report["padded_segment_count"], 1)
            self.assertEqual(report["segments"][2]["scale_mode"], "downscale_to_fit")
            self.assertTrue(report["segments"][2]["needs_padding"])

    def test_static_workbench_entry_exists(self) -> None:
        index_path = _SproutApiHandler._resolve_static_file_path("/")
        script_path = _SproutApiHandler._resolve_static_file_path("/pages/index.js")
        node_path = _SproutApiHandler._resolve_static_file_path("/pages/node.html")
        node_script_path = _SproutApiHandler._resolve_static_file_path("/pages/node.js")

        self.assertTrue(index_path.exists())
        self.assertTrue(script_path.exists())
        self.assertTrue(node_path.exists())
        self.assertTrue(node_script_path.exists())
        self.assertEqual(index_path.name, "index.html")


if __name__ == "__main__":
    unittest.main()
