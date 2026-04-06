"""Sprout HTTP API。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.parse import parse_qs, urlsplit

from .directory_picker import SproutDirectoryPicker
from .media import SproutMediaService
from .project_service import SproutProjectService
from .workflow_service import SproutWorkflowService


@dataclass
class SproutHttpApi:
    """将一期后端能力暴露为简单 HTTP API。"""

    project_service: SproutProjectService | None = None
    workflow_service: SproutWorkflowService | None = None
    media_service: SproutMediaService | None = None
    directory_picker: SproutDirectoryPicker | None = None

    def handle_request(
        self,
        *,
        method: str,
        raw_path: str,
        body: bytes | None = None,
    ) -> tuple[int, dict[str, str], bytes]:
        try:
            parsed_url = urlsplit(raw_path)
            path_parts = [part for part in parsed_url.path.split("/") if part]
            query_params = parse_qs(parsed_url.query)
            json_body = self._load_json_body(body)

            if path_parts == ["api", "health"] and method == "GET":
                return self._json_response(200, {"status": "ok"})

            if path_parts == ["api", "projects"] and method == "GET":
                return self._json_response(200, {"projects": self._get_project_service().list_projects()})

            if path_parts == ["api", "projects", "import"] and method == "POST":
                project_root = str(json_body.get("project_root") or "").strip()
                import_mode = str(json_body.get("import_mode") or "reference").strip()
                payload = self._get_project_service().import_project(
                    project_root,
                    import_mode=import_mode,
                )
                return self._json_response(200, payload)

            if path_parts == ["api", "projects", "select-directory"] and method == "POST":
                payload = self._get_directory_picker().pick_directory()
                return self._json_response(200, payload)

            if len(path_parts) >= 3 and path_parts[:2] == ["api", "projects"]:
                project_id = path_parts[2]

                if len(path_parts) == 3 and method == "GET":
                    return self._json_response(
                        200,
                        self._get_project_service().get_project_detail(project_id),
                    )

                if path_parts[3:] == ["versions"] and method == "GET":
                    payload = self._get_project_service().list_versions(
                        project_id,
                        node_type=self._read_single_query_value(query_params, "node_type"),
                        node_key=self._read_single_query_value(query_params, "node_key"),
                    )
                    return self._json_response(200, {"versions": payload})

                if len(path_parts) == 5 and path_parts[3] == "versions" and method == "GET":
                    payload = self._get_project_service().get_version_detail(project_id, path_parts[4])
                    return self._json_response(200, payload)

                if path_parts[3:] == ["activate"] and method == "POST":
                    version_id = str(json_body.get("version_id") or "").strip()
                    payload = self._get_project_service().activate_version(project_id, version_id)
                    return self._json_response(200, payload)

                if path_parts[3:] == ["nodes", "detail"] and method == "GET":
                    node_type = self._read_single_query_value(query_params, "node_type")
                    node_key = self._read_single_query_value(query_params, "node_key") or "project"
                    if not node_type:
                        raise ValueError("nodes/detail 必须提供 node_type 查询参数。")
                    payload = self._get_project_service().get_node_detail(
                        project_id,
                        node_type=node_type,
                        node_key=node_key,
                    )
                    return self._json_response(200, payload)

                if path_parts[3:] == ["nodes", "run"] and method == "POST":
                    raw_user_input_payload = json_body.get("user_input_payload")
                    payload = self._get_workflow_service().run_node(
                        project_id=project_id,
                        node_type=str(json_body.get("node_type") or "").strip(),
                        node_key=str(json_body.get("node_key") or "project").strip() or "project",
                        source_version_id=self._read_optional_body_value(json_body, "source_version_id"),
                        force=bool(json_body.get("force") or False),
                        extra_reference_count=int(json_body.get("extra_reference_count") or 0),
                        user_input_payload=(
                            raw_user_input_payload if isinstance(raw_user_input_payload, dict) else None
                        ),
                    )
                    return self._json_response(200, payload)

                if len(path_parts) == 5 and path_parts[3] == "runs" and method == "GET":
                    payload = self._get_project_service().get_run_detail(project_id, path_parts[4])
                    return self._json_response(200, payload)

                if path_parts[3:] == ["media"] and method == "GET":
                    asset_path = self._read_single_query_value(query_params, "path")
                    if not asset_path:
                        raise ValueError("media 接口必须提供 path 查询参数。")
                    mime_type, file_bytes = self._get_media_service().read_project_media(project_id, asset_path)
                    return 200, {"Content-Type": mime_type}, file_bytes

            return self._json_response(404, {"error": "接口不存在。"})
        except Exception as exc:
            return self._handle_exception(exc)

    @staticmethod
    def _load_json_body(body: bytes | None) -> dict[str, object]:
        if not body:
            return {}
        payload = json.loads(body.decode("utf-8"))
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _read_single_query_value(query_params: dict[str, list[str]], key: str) -> str | None:
        values = query_params.get(key) or []
        if not values:
            return None
        normalized_value = values[0].strip()
        return normalized_value or None

    @staticmethod
    def _read_optional_body_value(payload: dict[str, object], key: str) -> str | None:
        value = payload.get(key)
        if value is None:
            return None
        normalized_value = str(value).strip()
        return normalized_value or None

    @staticmethod
    def _json_response(status_code: int, payload: dict[str, object]) -> tuple[int, dict[str, str], bytes]:
        return (
            status_code,
            {"Content-Type": "application/json; charset=utf-8"},
            json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"),
        )

    def _handle_exception(self, exc: Exception) -> tuple[int, dict[str, str], bytes]:
        if isinstance(exc, KeyError):
            return self._json_response(404, {"error": str(exc)})
        if isinstance(exc, FileNotFoundError):
            return self._json_response(404, {"error": str(exc)})
        if isinstance(exc, PermissionError):
            return self._json_response(403, {"error": str(exc)})
        if isinstance(exc, ValueError):
            return self._json_response(400, {"error": str(exc)})
        return self._json_response(500, {"error": str(exc)})

    def _get_project_service(self) -> SproutProjectService:
        if self.project_service is None:
            self.project_service = SproutProjectService()
        return self.project_service

    def _get_workflow_service(self) -> SproutWorkflowService:
        if self.workflow_service is None:
            self.workflow_service = SproutWorkflowService()
        return self.workflow_service

    def _get_media_service(self) -> SproutMediaService:
        if self.media_service is None:
            self.media_service = SproutMediaService()
        return self.media_service

    def _get_directory_picker(self) -> SproutDirectoryPicker:
        if self.directory_picker is None:
            self.directory_picker = SproutDirectoryPicker()
        return self.directory_picker
