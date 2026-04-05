"""Sprout 一期后端能力测试。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from urllib.parse import quote

from agents.sprout import (
    SproutExporter,
    SproutJimengPackager,
    SproutProjectStore,
    SproutRunStore,
    SproutVersionStore,
)
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

    def test_static_workbench_entry_exists(self) -> None:
        index_path = _SproutApiHandler._resolve_static_file_path("/")
        script_path = _SproutApiHandler._resolve_static_file_path("/pages/index.js")

        self.assertTrue(index_path.exists())
        self.assertTrue(script_path.exists())
        self.assertEqual(index_path.name, "index.html")


if __name__ == "__main__":
    unittest.main()
