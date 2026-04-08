"""Sprout 一期后端能力测试（纯云端模式）。

使用 FakeTableService 和 FakeStorageService 模拟 Supabase，
验证 SproutProjectService / SproutWorkflowService 的云端集成逻辑。
"""

from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import patch
from urllib.parse import quote

from agents.sprout import (
    SproutAsset,
    SproutProjectBundle,
    SproutProjectStore,
)
from agents.sprout.core.video_merger import SproutVideoMerger
from agents.sprout.service.cloud_asset_store import SproutCloudAssetStore
from agents.sprout.service.cloud_project_store import SproutCloudProjectStore
from agents.sprout.service.cloud_run_store import SproutCloudRunStore
from agents.sprout.service.cloud_version_store import SproutCloudVersionStore
from agents.sprout.service.http_api import SproutHttpApi
from agents.sprout.service.http_server import _SproutApiHandler
from agents.sprout.service.media import SproutMediaService
from agents.sprout.service.project_service import SproutProjectService
from agents.sprout.service.workflow_service import SproutWorkflowService
from agents.sprout.service.types import (
    SproutImportedProjectRecord,
    SproutNodeVersionRecord,
    build_runtime_id,
)
from agents.sprout.service.auth_service import SproutSessionContext, SproutSessionResolution
from agents.sprout.tests.test_sprout_smoke import build_demo_bundle
from module.database.Supabase.project_tables import SupabaseTableFilter

TEST_USER_ID = "test-user-id"


# ──────────────────────────────────────────────────────────
# 假认证服务
# ──────────────────────────────────────────────────────────


@dataclass
class FakeAuthService:
    """测试用认证服务，始终返回固定的测试用户上下文。"""

    context: SproutSessionContext = field(default_factory=lambda: SproutSessionContext(
        user_id=TEST_USER_ID,
        email="tester@example.com",
        user_payload={"id": TEST_USER_ID, "email": "tester@example.com"},
        session_payload={"access_token": "fake-access-token", "refresh_token": "fake-refresh-token"},
    ))

    def resolve_session_from_headers(self, headers):
        return SproutSessionResolution(context=self.context)

    def login_with_password(self, *, email: str, password: str):
        return self.context, "sprout_session=fake-session; Path=/; HttpOnly"

    def logout_from_headers(self, headers):
        return "sprout_session=; Path=/; Max-Age=0; HttpOnly"


# ──────────────────────────────────────────────────────────
# 内存版表服务（替代 SupabaseProjectTableService）
# ──────────────────────────────────────────────────────────


class FakeTableService:
    """内存版表服务，模拟 SupabaseProjectTableService 的增删改查。"""

    def __init__(self) -> None:
        self._tables: dict[str, list[dict[str, Any]]] = {}

    def select_rows(
        self,
        table_name: str,
        *,
        columns: str = "*",
        filters: list[SupabaseTableFilter] | None = None,
        order_by: str | None = None,
        limit: int | None = None,
        single: bool = False,
    ) -> Any:
        rows = [dict(row) for row in self._tables.get(table_name, [])]
        if filters:
            for f in filters:
                rows = [row for row in rows if self._match_filter(row, f)]
        if order_by:
            col, direction = self._parse_order_by(order_by)
            rows.sort(key=lambda r: str(r.get(col, "")), reverse=(direction == "desc"))
        if limit is not None:
            rows = rows[:limit]
        if single:
            return rows[0] if rows else None
        return rows

    def insert_rows(
        self,
        table_name: str,
        rows: list[dict[str, Any]] | dict[str, Any],
    ) -> Any:
        payload = rows if isinstance(rows, list) else [rows]
        self._tables.setdefault(table_name, []).extend(dict(r) for r in payload)
        return payload

    def upsert_rows(
        self,
        table_name: str,
        rows: list[dict[str, Any]] | dict[str, Any],
        *,
        on_conflict: tuple[str, ...] | None = None,
    ) -> Any:
        payload = rows if isinstance(rows, list) else [rows]
        table = self._tables.setdefault(table_name, [])
        result: list[dict[str, Any]] = []
        for new_row in payload:
            if on_conflict:
                idx = self._find_conflict_index(table, new_row, on_conflict)
                if idx is not None:
                    table[idx].update(new_row)
                    result.append(dict(table[idx]))
                    continue
            table.append(dict(new_row))
            result.append(dict(new_row))
        return result

    def update_rows(
        self,
        table_name: str,
        *,
        values: dict[str, Any],
        filters: list[SupabaseTableFilter],
    ) -> Any:
        table = self._tables.get(table_name, [])
        updated: list[dict[str, Any]] = []
        for row in table:
            if all(self._match_filter(row, f) for f in filters):
                row.update(values)
                updated.append(dict(row))
        return updated

    def delete_rows(
        self,
        table_name: str,
        *,
        filters: list[SupabaseTableFilter],
    ) -> Any:
        table = self._tables.get(table_name, [])
        to_delete = [row for row in table if all(self._match_filter(row, f) for f in filters)]
        for row in to_delete:
            table.remove(row)
        return to_delete

    @staticmethod
    def _find_conflict_index(
        table: list[dict[str, Any]],
        new_row: dict[str, Any],
        conflict_keys: tuple[str, ...],
    ) -> int | None:
        for idx, existing in enumerate(table):
            if all(existing.get(k) == new_row.get(k) for k in conflict_keys):
                return idx
        return None

    @staticmethod
    def _match_filter(row: dict[str, Any], f: SupabaseTableFilter) -> bool:
        value = row.get(f.column)
        if f.operator == "eq":
            return value == f.value
        if f.operator == "neq":
            return value != f.value
        if f.operator == "in":
            return value in (f.value if isinstance(f.value, (list, tuple, set)) else [f.value])
        if f.operator == "is":
            return value is f.value
        if f.operator == "gt":
            return value > f.value
        if f.operator == "gte":
            return value >= f.value
        if f.operator == "lt":
            return value < f.value
        if f.operator == "lte":
            return value <= f.value
        return True

    @staticmethod
    def _parse_order_by(order_by: str) -> tuple[str, str]:
        parts = order_by.rsplit(".", 1)
        return (parts[0], parts[1]) if len(parts) == 2 else (parts[0], "asc")


# ──────────────────────────────────────────────────────────
# 内存版存储服务（替代 SupabaseStorageService）
# ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class _FakeStorageConfig:
    bucket_name: str = "test-bucket"
    path_prefix: str = "projects"
    signed_url_ttl_seconds: int = 3600
    public_bucket: bool = False


class FakeStorageService:
    """内存版存储服务，模拟 SupabaseStorageService 的上传/下载/签名。"""

    def __init__(self) -> None:
        self._objects: dict[str, bytes] = {}
        self.storage_config = _FakeStorageConfig()

    @property
    def bucket_name(self) -> str:
        return self.storage_config.bucket_name

    def upload_bytes(
        self,
        *,
        object_path: str,
        content: bytes,
        content_type: str = "application/octet-stream",
        upsert: bool = False,
        bearer_token: str | None = None,
    ) -> dict[str, Any]:
        self._objects[object_path] = content
        return {"bucket_name": self.bucket_name, "object_path": object_path}

    def upload_text(
        self,
        *,
        object_path: str,
        content: str,
        content_type: str = "application/json; charset=utf-8",
        upsert: bool = True,
        bearer_token: str | None = None,
    ) -> dict[str, Any]:
        return self.upload_bytes(
            object_path=object_path,
            content=content.encode("utf-8"),
            content_type=content_type,
            upsert=upsert,
        )

    def upload_file(
        self,
        *,
        file_path: str | Path,
        object_path: str,
        content_type: str | None = None,
        upsert: bool = False,
        bearer_token: str | None = None,
    ) -> dict[str, Any]:
        data = Path(file_path).read_bytes()
        return self.upload_bytes(
            object_path=object_path,
            content=data,
            content_type=content_type or "application/octet-stream",
            upsert=upsert,
        )

    def download_object(
        self,
        *,
        object_path: str,
        bearer_token: str | None = None,
    ) -> bytes:
        if object_path not in self._objects:
            raise KeyError(f"对象不存在：{object_path}")
        return self._objects[object_path]

    def create_signed_url(
        self,
        *,
        object_path: str,
        expires_in: int | None = None,
        bearer_token: str | None = None,
    ) -> str:
        return f"https://fake-storage.example.com/{self.bucket_name}/{object_path}?token=fake"

    def build_public_url(self, object_path: str) -> str:
        return f"https://fake-storage.example.com/{self.bucket_name}/{object_path}"

    def build_asset_object_path(
        self,
        *,
        project_id: str,
        asset_type: str,
        asset_id: str,
        file_name: str,
    ) -> str:
        prefix = self.storage_config.path_prefix
        return f"{prefix}/{project_id}/assets/{asset_type}/{asset_id}/{file_name}"

    def build_snapshot_object_path(
        self,
        *,
        project_id: str,
        snapshot_type: str,
        file_name: str,
    ) -> str:
        prefix = self.storage_config.path_prefix
        return f"{prefix}/{project_id}/snapshots/{snapshot_type}/{file_name}"

    def build_log_object_path(
        self,
        *,
        project_id: str,
        run_id: str,
        file_name: str | None = None,
    ) -> str:
        prefix = self.storage_config.path_prefix
        actual_file = file_name or f"{run_id}.log"
        return f"{prefix}/{project_id}/logs/{run_id}/{actual_file}"

    def ensure_bucket_exists(self) -> None:
        pass


# ──────────────────────────────────────────────────────────
# 测试用例
# ──────────────────────────────────────────────────────────


class SproutBackendPhase1Test(unittest.TestCase):

    def _build_services(self, temp_root: Path):
        """构建所有服务，使用 Fake 替代真实 Supabase。"""

        fake_table = FakeTableService()
        fake_storage = FakeStorageService()

        cloud_project_store = SproutCloudProjectStore(
            table_service=fake_table,
            storage_service=fake_storage,
        )
        cloud_version_store = SproutCloudVersionStore(
            table_service=fake_table,
        )
        cloud_run_store = SproutCloudRunStore(
            table_service=fake_table,
            storage_service=fake_storage,
        )
        cloud_asset_store = SproutCloudAssetStore(
            table_service=fake_table,
            storage_service=fake_storage,
        )

        project_service = SproutProjectService(
            cloud_project_store=cloud_project_store,
            cloud_version_store=cloud_version_store,
            cloud_run_store=cloud_run_store,
        )
        workflow_service = SproutWorkflowService(
            cloud_project_store=cloud_project_store,
            cloud_version_store=cloud_version_store,
            cloud_run_store=cloud_run_store,
            cloud_asset_store=cloud_asset_store,
        )
        media_service = SproutMediaService(
            cloud_asset_store=cloud_asset_store,
            storage_service=fake_storage,
        )
        api = SproutHttpApi(
            project_service=project_service,
            workflow_service=workflow_service,
            media_service=media_service,
            auth_service=FakeAuthService(),
        )
        return project_service, workflow_service, media_service, api

    def _seed_project_to_cloud(
        self,
        *,
        bundle: SproutProjectBundle,
        project_root: Path,
        project_service: SproutProjectService,
        create_initial_version: bool = False,
        user_id: str = TEST_USER_ID,
    ) -> SproutImportedProjectRecord:
        """将 demo bundle 写入假云端存储并返回项目记录。

        create_initial_version=True 时同时为 user_input 节点生成初始版本。
        """

        store = SproutProjectStore()
        store.save_bundle(bundle, output_root=project_root)

        record = SproutImportedProjectRecord(
            project_id=bundle.project_name,
            project_type="sprout",
            display_name=bundle.episode.title,
            project_name=bundle.project_name,
            project_root=str(project_root),
            canonical_root=str(project_root),
            bundle_path=str(project_root / "script" / "bundle.json"),
        )

        cloud_project_store = project_service.cloud_project_store
        cloud_project_store.upsert_project_record(record, bundle=bundle, created_by=user_id)
        cloud_project_store.add_project_member(
            project_id=record.project_id,
            user_id=user_id,
            role="owner",
        )
        snapshot_row = cloud_project_store.save_bundle_snapshot(
            project_id=record.project_id,
            project_bundle=bundle,
        )

        if create_initial_version:
            snapshot_id = str(snapshot_row.get("snapshot_id") or "").strip()
            version_id = build_runtime_id("ver")
            project_service.cloud_version_store.upsert_version_record(
                SproutNodeVersionRecord(
                    version_id=version_id,
                    project_id=record.project_id,
                    node_type="user_input",
                    node_key="project",
                    bundle_snapshot_path="",
                    status="ready",
                ),
                snapshot_id=snapshot_id,
            )
            cloud_project_store.update_active_state(
                record.project_id,
                {
                    "selected_versions": {"user_input:project": version_id},
                    "active_bundle_version_id": version_id,
                    "active_bundle_snapshot_id": snapshot_id,
                },
            )

        return record

    @staticmethod
    def _get_node(nodes: list[dict[str, object]], node_id: str) -> dict[str, object]:
        for node in nodes:
            if node["node_id"] == node_id:
                return node
        raise AssertionError(f"未找到节点：{node_id}")

    # ──────────────────────────────────────────────────────
    # 云端项目创建与查询
    # ──────────────────────────────────────────────────────

    def test_create_project_in_cloud(self) -> None:
        """验证项目写入云端后，list / detail 接口正确返回摘要。"""

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            project_root = temp_root / "demo_project"
            project_root.mkdir(parents=True, exist_ok=True)
            bundle = build_demo_bundle(project_root)

            project_service, _, _, _ = self._build_services(temp_root)
            record = self._seed_project_to_cloud(
                bundle=bundle,
                project_root=project_root,
                project_service=project_service,
            )

            listed_projects = project_service.list_projects_for_user(TEST_USER_ID)
            project_detail = project_service.get_project_detail_for_user(TEST_USER_ID, record.project_id)

            self.assertEqual(len(listed_projects), 1)
            self.assertEqual(listed_projects[0]["display_name"], "测试项目")
            self.assertEqual(project_detail["bundle"]["episode"]["title"], "测试项目")
            self.assertEqual(len(project_detail["bundle"]["characters"]), 2)
            self.assertEqual(project_detail["bundle"]["characters"][0]["name"], "沈清辞")

    # ──────────────────────────────────────────────────────
    # 节点执行与版本创建
    # ──────────────────────────────────────────────────────

    def test_run_prepare_shot_with_cloud_stores(self) -> None:
        """验证 prepare_shot 节点通过云端存储正确执行，并生成版本与日志。"""

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            project_root = temp_root / "demo_project"
            project_root.mkdir(parents=True, exist_ok=True)
            bundle = build_demo_bundle(project_root)

            project_service, workflow_service, _, _ = self._build_services(temp_root)
            record = self._seed_project_to_cloud(
                bundle=bundle,
                project_root=project_root,
                project_service=project_service,
            )

            run_payload = workflow_service.run_node(
                project_id=record.project_id,
                node_type="prepare_shot",
                node_key="shot_001",
            )

            project_detail = project_service.get_project_detail_for_user(TEST_USER_ID, record.project_id)
            run_detail = project_service.get_run_detail_for_user(
                TEST_USER_ID,
                record.project_id,
                run_payload["run"]["run_id"],
            )

            self.assertEqual(run_payload["run"]["status"], "success")
            self.assertIsNotNone(run_payload["version"]["version_id"])
            self.assertTrue(project_detail["versions"])
            self.assertIn("执行节点类型", run_detail["log"])
            self.assertEqual(
                project_detail["bundle"]["shots"][0]["status"],
                "prompt_ready",
            )

    # ──────────────────────────────────────────────────────
    # HTTP API
    # ──────────────────────────────────────────────────────

    def test_http_api_exposes_run_and_media(self) -> None:
        """验证 HTTP API 的节点执行、版本查询和媒体签名 URL（云端模式）。"""

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            project_root = temp_root / "demo_project"
            project_root.mkdir(parents=True, exist_ok=True)
            bundle = build_demo_bundle(project_root)

            project_service, _, _, api = self._build_services(temp_root)
            record = self._seed_project_to_cloud(
                bundle=bundle,
                project_root=project_root,
                project_service=project_service,
            )
            project_id = record.project_id

            # 执行 prepare_shot 节点（同时会上传角色资产）
            status_code, _, response_body = api.handle_request(
                method="POST",
                raw_path=f"/api/projects/{project_id}/nodes/run",
                body=json.dumps(
                    {"node_type": "prepare_shot", "node_key": "shot_001"},
                    ensure_ascii=False,
                ).encode("utf-8"),
            )
            run_payload = json.loads(response_body.decode("utf-8"))
            self.assertEqual(status_code, 200)
            self.assertEqual(run_payload["run"]["status"], "success")

            # 查询节点详情
            status_code, _, response_body = api.handle_request(
                method="GET",
                raw_path=f"/api/projects/{project_id}/nodes/detail?node_type=prepare_shot&node_key=shot_001",
            )
            node_detail = json.loads(response_body.decode("utf-8"))
            self.assertEqual(status_code, 200)
            self.assertEqual(node_detail["node"]["node_type"], "prepare_shot")

            # 查询版本详情
            version_id = run_payload["version"]["version_id"]
            status_code, _, response_body = api.handle_request(
                method="GET",
                raw_path=f"/api/projects/{project_id}/versions/{version_id}",
            )
            version_detail = json.loads(response_body.decode("utf-8"))
            self.assertEqual(status_code, 200)
            self.assertEqual(version_detail["version"]["version_id"], version_id)

            # 查询媒体（角色锚图从云端 Storage 下载字节流）
            shen_path = str(project_root / "characters" / "shen.png")
            status_code, headers, media_body = api.handle_request(
                method="GET",
                raw_path=f"/api/projects/{project_id}/media?path={quote(shen_path)}",
            )
            self.assertEqual(status_code, 200)
            self.assertEqual(headers["Content-Type"], "image/png")
            self.assertTrue(len(media_body) > 0)

    # ──────────────────────────────────────────────────────
    # 版本链追踪与节点状态刷新
    # ──────────────────────────────────────────────────────

    def test_project_detail_status_tracks_version_chain_freshness(self) -> None:
        """验证版本链追踪：上游更新时，下游节点正确变为 pending/waiting。"""

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            project_root = temp_root / "demo_project"
            project_root.mkdir(parents=True, exist_ok=True)
            bundle = build_demo_bundle(project_root)

            project_service, workflow_service, _, _ = self._build_services(temp_root)
            record = self._seed_project_to_cloud(
                bundle=bundle,
                project_root=project_root,
                project_service=project_service,
                create_initial_version=True,
            )
            project_id = record.project_id

            initial_detail = project_service.get_project_detail_for_user(TEST_USER_ID, project_id)
            user_input_version_id = self._get_node(
                initial_detail["nodes"],
                "user_input:project",
            )["active_version_id"]
            self.assertIsNotNone(user_input_version_id)

            # 执行 characters → prepare_shot → generate_shot（fake）
            character_v1 = workflow_service.run_node(
                project_id=project_id,
                node_type="characters",
            )
            prepare_v1 = workflow_service.run_node(
                project_id=project_id,
                node_type="prepare_shot",
                node_key="shot_001",
            )

            def fake_generate_shots(self_wf, *, project_bundle, output_root, **kwargs):
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
                return project_bundle

            with patch(
                "agents.sprout.core.orchestration.SproutWorkflow.generate_shots",
                new=fake_generate_shots,
            ):
                generate_v1 = workflow_service.run_node(
                    project_id=project_id,
                    node_type="generate_shot",
                    node_key="shot_001",
                )

            # 验证依赖版本链
            self.assertEqual(
                character_v1["version"]["dependency_version_ids"],
                {"user_input:project": user_input_version_id},
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

            # 验证当前节点状态
            project_detail = project_service.get_project_detail_for_user(TEST_USER_ID, project_id)
            self.assertEqual(
                self._get_node(project_detail["nodes"], "user_input:project")["status"],
                "ready",
            )
            self.assertEqual(
                self._get_node(project_detail["nodes"], "script_storyboard:project")["active_version_id"],
                user_input_version_id,
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

            # 重新运行 characters → 下游节点应变为 stale
            character_v2 = workflow_service.run_node(
                project_id=project_id,
                node_type="characters",
            )
            project_detail = project_service.get_project_detail_for_user(TEST_USER_ID, project_id)
            self.assertEqual(
                self._get_node(project_detail["nodes"], "prepare_shot:shot_001")["status"],
                "pending",
            )
            self.assertEqual(
                self._get_node(project_detail["nodes"], "generate_shot:shot_001")["status"],
                "waiting",
            )

            # 重新运行 prepare_shot → 依赖链更新
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

            project_detail = project_service.get_project_detail_for_user(TEST_USER_ID, project_id)
            self.assertEqual(
                self._get_node(project_detail["nodes"], "prepare_shot:shot_001")["status"],
                "prompt_ready",
            )
            self.assertEqual(
                self._get_node(project_detail["nodes"], "generate_shot:shot_001")["status"],
                "pending",
            )

            # 验证节点详情
            node_detail = project_service.get_node_detail_for_user(
                TEST_USER_ID,
                project_id,
                node_type="generate_shot",
                node_key="shot_001",
            )
            self.assertEqual(node_detail["node"]["status"], "pending")

    # ──────────────────────────────────────────────────────
    # script_storyboard 节点版本复用
    # ──────────────────────────────────────────────────────

    def test_script_storyboard_node_reuses_user_input_versions(self) -> None:
        """验证 script_storyboard 节点复用 user_input 版本。"""

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            project_root = temp_root / "demo_project"
            project_root.mkdir(parents=True, exist_ok=True)
            bundle = build_demo_bundle(project_root)

            project_service, _, _, _ = self._build_services(temp_root)
            record = self._seed_project_to_cloud(
                bundle=bundle,
                project_root=project_root,
                project_service=project_service,
                create_initial_version=True,
            )

            project_detail = project_service.get_project_detail_for_user(TEST_USER_ID, record.project_id)
            user_input_node = self._get_node(project_detail["nodes"], "user_input:project")
            script_storyboard_node = self._get_node(project_detail["nodes"], "script_storyboard:project")

            self.assertEqual(
                script_storyboard_node["active_version_id"],
                user_input_node["active_version_id"],
            )

            node_detail = project_service.get_node_detail_for_user(
                TEST_USER_ID,
                record.project_id,
                node_type="script_storyboard",
                node_key="project",
            )
            self.assertTrue(node_detail["versions"])
            self.assertEqual(
                node_detail["versions"][0]["version_id"],
                user_input_node["active_version_id"],
            )
            self.assertEqual(node_detail["node"]["payload"]["episode"]["title"], "测试项目")
            self.assertEqual(len(node_detail["node"]["payload"]["shots"]), 1)

    # ──────────────────────────────────────────────────────
    # 静态页面与 session
    # ──────────────────────────────────────────────────────

    def test_static_workbench_entry_exists(self) -> None:
        """验证静态页面文件存在。"""

        index_path = _SproutApiHandler._resolve_static_file_path("/")
        script_path = _SproutApiHandler._resolve_static_file_path("/pages/index.js")
        login_path = _SproutApiHandler._resolve_static_file_path("/pages/login.html")
        node_path = _SproutApiHandler._resolve_static_file_path("/pages/node.html")
        node_script_path = _SproutApiHandler._resolve_static_file_path("/pages/node.js")

        self.assertTrue(index_path.exists())
        self.assertTrue(script_path.exists())
        self.assertTrue(login_path.exists())
        self.assertTrue(node_path.exists())
        self.assertTrue(node_script_path.exists())
        self.assertEqual(index_path.name, "login.html")

    def test_http_api_exposes_session_and_logout(self) -> None:
        """验证 HTTP API 的登录态和登出。"""

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            _, _, _, api = self._build_services(temp_root)

            status_code, _, response_body = api.handle_request(
                method="GET",
                raw_path="/api/session",
                headers={"Cookie": "sprout_session=fake"},
            )
            payload = json.loads(response_body.decode("utf-8"))
            self.assertEqual(status_code, 200)
            self.assertEqual(payload["user"]["email"], "tester@example.com")

            status_code, headers, _ = api.handle_request(
                method="POST",
                raw_path="/api/logout",
                body=json.dumps({}, ensure_ascii=False).encode("utf-8"),
                headers={"Cookie": "sprout_session=fake"},
            )
            self.assertEqual(status_code, 200)
            self.assertIn("Set-Cookie", headers)

    # ──────────────────────────────────────────────────────
    # 视频合并分辨率策略
    # ──────────────────────────────────────────────────────

    def test_video_merger_prefers_non_upscale_target_resolution(self) -> None:
        """验证视频合并器优先选择无需放大的输出分辨率。"""

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


if __name__ == "__main__":
    unittest.main()
