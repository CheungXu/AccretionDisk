"""Sprout 二期云端模型与 Supabase 模块测试。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agents.sprout.service.cloud_asset_store import SproutCloudAssetStore
from agents.sprout.service.cloud_project_store import SproutCloudProjectStore
from agents.sprout.service.cloud_run_store import SproutCloudRunStore
from agents.sprout.service.cloud_version_store import SproutCloudVersionStore
from agents.sprout.service.types import (
    SproutImportedProjectRecord,
    SproutNodeVersionRecord,
    SproutRunRecord,
)
from agents.sprout.tests.test_sprout_smoke import build_demo_bundle
from module.database.Supabase import (
    PROJECT_ACTION_ASSET_UPLOAD,
    PROJECT_ACTION_MEMBER_MANAGE,
    PROJECT_ACTION_READ,
    PROJECT_ACTION_UPDATE,
    PROJECT_ROLE_EDITOR,
    PROJECT_ROLE_OWNER,
    PROJECT_ROLE_VIEWER,
    SupabaseRestClient,
    SupabaseStorageConfig,
    SupabaseStorageObjectRef,
    SupabaseStorageService,
    build_role_capability_report,
    get_minimum_role_for_action,
    role_has_action,
)


class SproutBackendPhase2Test(unittest.TestCase):
    def test_minimal_role_model_maps_actions(self) -> None:
        self.assertTrue(role_has_action(PROJECT_ROLE_OWNER, PROJECT_ACTION_MEMBER_MANAGE))
        self.assertTrue(role_has_action(PROJECT_ROLE_EDITOR, PROJECT_ACTION_UPDATE))
        self.assertTrue(role_has_action(PROJECT_ROLE_EDITOR, PROJECT_ACTION_ASSET_UPLOAD))
        self.assertTrue(role_has_action(PROJECT_ROLE_VIEWER, PROJECT_ACTION_READ))
        self.assertFalse(role_has_action(PROJECT_ROLE_VIEWER, PROJECT_ACTION_UPDATE))
        self.assertEqual(get_minimum_role_for_action(PROJECT_ACTION_READ), PROJECT_ROLE_VIEWER)
        self.assertEqual(get_minimum_role_for_action(PROJECT_ACTION_UPDATE), PROJECT_ROLE_EDITOR)
        capability_roles = [item.role for item in build_role_capability_report()]
        self.assertEqual(capability_roles, [PROJECT_ROLE_OWNER, PROJECT_ROLE_EDITOR, PROJECT_ROLE_VIEWER])

    def test_storage_service_builds_project_scoped_paths(self) -> None:
        client = SupabaseRestClient(url="https://example.supabase.co", api_key="demo-key")
        storage = SupabaseStorageService(
            client=client,
            storage_config=SupabaseStorageConfig(
                bucket_name="sprout-projects",
                path_prefix="projects",
                signed_url_ttl_seconds=3600,
                public_bucket=False,
            ),
        )

        asset_path = storage.build_asset_object_path(
            project_id="sprout_demo",
            asset_type="shot_video",
            asset_id="shot_001_video_01",
            file_name="shot_001_01.mp4",
        )
        snapshot_path = storage.build_snapshot_object_path(
            project_id="sprout_demo",
            snapshot_type="bundle",
            file_name="bundle.json",
        )
        log_path = storage.build_log_object_path(
            project_id="sprout_demo",
            run_id="run_prepare_shot_001",
        )

        self.assertEqual(
            asset_path,
            "projects/sprout_demo/assets/shot_video/shot_001_video_01/shot_001_01.mp4",
        )
        self.assertEqual(
            snapshot_path,
            "projects/sprout_demo/snapshots/bundle/bundle.json",
        )
        self.assertEqual(
            log_path,
            "projects/sprout_demo/logs/run_prepare_shot_001/run_prepare_shot_001.log",
        )

    def test_cloud_project_store_builds_project_and_member_rows(self) -> None:
        record = SproutImportedProjectRecord(
            project_id="sprout_demo",
            project_type="sprout",
            display_name="测试项目",
            project_name="sprout_demo",
            project_root="data/sprout/demo",
            canonical_root="data/sprout/demo",
            bundle_path="data/sprout/demo/script/bundle.json",
            manifest_path="data/sprout/demo/manifest/manifest.json",
            cover_asset_path="data/sprout/demo/videos/final.mp4",
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            bundle = build_demo_bundle(Path(temp_dir))
            store = SproutCloudProjectStore()
            project_row = store.build_project_row(record, bundle=bundle, created_by="user-1")
            member_row = store.build_project_member_row(
                project_id=record.project_id,
                user_id="user-1",
                role="owner",
            )

        self.assertEqual(project_row["project_id"], "sprout_demo")
        self.assertEqual(project_row["project_type"], "sprout")
        self.assertEqual(project_row["title"], bundle.episode.title)
        self.assertEqual(project_row["topic"], bundle.topic_input.topic)
        self.assertEqual(project_row["created_by"], "user-1")
        self.assertIn("local_paths", project_row["metadata"])
        self.assertEqual(member_row["role"], "owner")
        self.assertEqual(member_row["status"], "active")

    def test_cloud_asset_version_and_run_rows_keep_existing_ids(self) -> None:
        asset_store = SproutCloudAssetStore()
        version_store = SproutCloudVersionStore()
        run_store = SproutCloudRunStore()

        with tempfile.TemporaryDirectory() as temp_dir:
            asset = build_demo_bundle(Path(temp_dir)).assets[0]
            asset_row = asset_store.build_asset_row(
                asset,
                project_id="sprout_demo",
                object_ref=SupabaseStorageObjectRef(
                    bucket_name="sprout-projects",
                    object_path="projects/sprout_demo/assets/character_anchor/demo.png",
                ),
                character_id="char_001",
            )

            version_record = SproutNodeVersionRecord(
                version_id="version_prepare_shot_shot_001_202604080001",
                project_id="sprout_demo",
                node_type="prepare_shot",
                node_key="shot_001",
                bundle_snapshot_path="projects/sprout_demo/snapshots/node_version/version_prepare_shot_shot_001.json",
                source_version_id="version_characters_project_202604080000",
                run_id="run_prepare_shot_shot_001_202604080001",
                asset_ids=["asset_001"],
                shot_ids=["shot_001"],
                dependency_version_ids={"characters:project": "version_characters_project_202604080000"},
            )
            version_row = version_store.build_version_row(version_record, snapshot_id="snapshot_001")

            run_record = SproutRunRecord(
                run_id="run_prepare_shot_shot_001_202604080001",
                project_id="sprout_demo",
                node_type="prepare_shot",
                node_key="shot_001",
                log_path="projects/sprout_demo/logs/run_prepare_shot_shot_001.log",
                status="success",
                source_version_id="version_characters_project_202604080000",
                result_version_id="version_prepare_shot_shot_001_202604080001",
                shot_ids=["shot_001"],
            )
            run_row = run_store.build_run_row(
                run_record,
                log_object_ref=SupabaseStorageObjectRef(
                    bucket_name="sprout-projects",
                    object_path="projects/sprout_demo/logs/run_prepare_shot_shot_001.log",
                ),
            )

            self.assertEqual(asset_row["asset_id"], asset.asset_id)
            self.assertEqual(asset_row["project_id"], "sprout_demo")
            self.assertEqual(version_row["version_id"], version_record.version_id)
            self.assertEqual(version_row["snapshot_id"], "snapshot_001")
            self.assertEqual(run_row["run_id"], run_record.run_id)
            self.assertEqual(run_row["log_bucket_name"], "sprout-projects")
            self.assertEqual(run_row["status"], "success")


if __name__ == "__main__":
    unittest.main()
