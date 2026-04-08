"""Sprout HTTP API。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.parse import parse_qs, urlsplit

from module.database.Supabase import (
    PROJECT_ACTION_RUN_RETRY,
    PROJECT_ACTION_VERSION_ACTIVATE,
    role_has_action,
)

from .auth_service import SproutAuthService, SproutSessionContext
from .directory_picker import SproutDirectoryPicker
from .media import SproutMediaService
from .project_service import SproutProjectService
from .workflow_service import SproutWorkflowService


@dataclass
class SproutHttpApi:
    """将登录后的项目管理能力暴露为 HTTP API。"""

    project_service: SproutProjectService | None = None
    workflow_service: SproutWorkflowService | None = None
    media_service: SproutMediaService | None = None
    directory_picker: SproutDirectoryPicker | None = None
    auth_service: SproutAuthService | None = None

    def handle_request(
        self,
        *,
        method: str,
        raw_path: str,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, str], bytes]:
        try:
            parsed_url = urlsplit(raw_path)
            path_parts = [part for part in parsed_url.path.split("/") if part]
            query_params = parse_qs(parsed_url.query)
            json_body = self._load_json_body(body)

            session_resolution = self._get_auth_service().resolve_session_from_headers(headers)
            response_headers = self._collect_auth_headers(session_resolution)
            current_user = session_resolution.context

            if path_parts == ["api", "health"] and method == "GET":
                return self._json_response(200, {"status": "ok"}, extra_headers=response_headers)

            if path_parts == ["api", "login"] and method == "POST":
                email = str(json_body.get("email") or "").strip()
                password = str(json_body.get("password") or "").strip()
                if not email or not password:
                    raise ValueError("登录必须提供 email 和 password。")
                context, set_cookie_header = self._get_auth_service().login_with_password(
                    email=email,
                    password=password,
                )
                login_headers = dict(response_headers)
                login_headers["Set-Cookie"] = set_cookie_header
                return self._json_response(
                    200,
                    {"user": self._serialize_session_user(context)},
                    extra_headers=login_headers,
                )

            if path_parts == ["api", "logout"] and method == "POST":
                logout_headers = dict(response_headers)
                logout_headers["Set-Cookie"] = self._get_auth_service().logout_from_headers(headers)
                return self._json_response(200, {"success": True}, extra_headers=logout_headers)

            if path_parts == ["api", "session"] and method == "GET":
                if current_user is None:
                    return self._json_response(401, {"error": "未登录。"}, extra_headers=response_headers)
                return self._json_response(
                    200,
                    {"user": self._serialize_session_user(current_user)},
                    extra_headers=response_headers,
                )

            if current_user is None:
                return self._json_response(401, {"error": "未登录。"}, extra_headers=response_headers)

            if path_parts == ["api", "projects"] and method == "GET":
                payload = self._get_project_service().list_projects_for_user(current_user.user_id)
                return self._json_response(200, {"projects": payload}, extra_headers=response_headers)

            if path_parts == ["api", "projects", "import"] and method == "POST":
                project_root = str(json_body.get("project_root") or "").strip()
                import_mode = str(json_body.get("import_mode") or "reference").strip()
                import_result = self._get_project_service().import_project_to_cloud(
                    project_root,
                    owner_user_id=current_user.user_id,
                    import_mode=import_mode,
                )
                project_id = str(import_result.get("project", {}).get("project_id") or "").strip()
                payload = (
                    self._get_project_service().get_project_summary_for_user(current_user.user_id, project_id)
                    if project_id
                    else import_result
                )
                if isinstance(payload, dict):
                    payload["cloud_import"] = import_result
                return self._json_response(200, payload, extra_headers=response_headers)

            if path_parts == ["api", "projects", "select-directory"] and method == "POST":
                payload = self._get_directory_picker().pick_directory()
                return self._json_response(200, payload, extra_headers=response_headers)

            if len(path_parts) >= 3 and path_parts[:2] == ["api", "projects"]:
                project_id = path_parts[2]

                if len(path_parts) == 3 and method == "GET":
                    payload = self._get_project_service().get_project_detail_for_user(
                        current_user.user_id,
                        project_id,
                    )
                    return self._json_response(200, payload, extra_headers=response_headers)

                if path_parts[3:] == ["versions"] and method == "GET":
                    payload = self._get_project_service().list_versions_for_user(
                        current_user.user_id,
                        project_id,
                        node_type=self._read_single_query_value(query_params, "node_type"),
                        node_key=self._read_single_query_value(query_params, "node_key"),
                    )
                    return self._json_response(200, {"versions": payload}, extra_headers=response_headers)

                if len(path_parts) == 5 and path_parts[3] == "versions" and method == "GET":
                    payload = self._get_project_service().get_version_detail_for_user(
                        current_user.user_id,
                        project_id,
                        path_parts[4],
                    )
                    return self._json_response(200, payload, extra_headers=response_headers)

                if path_parts[3:] == ["activate"] and method == "POST":
                    self._ensure_project_action(current_user.user_id, project_id, PROJECT_ACTION_VERSION_ACTIVATE)
                    version_id = str(json_body.get("version_id") or "").strip()
                    payload = self._get_project_service().activate_version_for_user(
                        current_user.user_id,
                        project_id,
                        version_id,
                    )
                    return self._json_response(200, payload, extra_headers=response_headers)

                if path_parts[3:] == ["nodes", "detail"] and method == "GET":
                    node_type = self._read_single_query_value(query_params, "node_type")
                    node_key = self._read_single_query_value(query_params, "node_key") or "project"
                    if not node_type:
                        raise ValueError("nodes/detail 必须提供 node_type 查询参数。")
                    payload = self._get_project_service().get_node_detail_for_user(
                        current_user.user_id,
                        project_id,
                        node_type=node_type,
                        node_key=node_key,
                    )
                    return self._json_response(200, payload, extra_headers=response_headers)

                if path_parts[3:] == ["nodes", "run"] and method == "POST":
                    self._ensure_project_action(current_user.user_id, project_id, PROJECT_ACTION_RUN_RETRY)
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
                    return self._json_response(200, payload, extra_headers=response_headers)

                if len(path_parts) == 5 and path_parts[3] == "runs" and method == "GET":
                    payload = self._get_project_service().get_run_detail_for_user(
                        current_user.user_id,
                        project_id,
                        path_parts[4],
                    )
                    return self._json_response(200, payload, extra_headers=response_headers)

                if path_parts[3:] == ["media"] and method == "GET":
                    asset_path = self._read_single_query_value(query_params, "path")
                    if not asset_path:
                        raise ValueError("media 接口必须提供 path 查询参数。")
                    mime_type, file_bytes = self._get_media_service().read_project_media(
                        project_id,
                        asset_path,
                    )
                    media_headers = {
                        "Content-Type": mime_type,
                        "Cache-Control": "no-store",
                    }
                    media_headers.update(response_headers)
                    return 200, media_headers, file_bytes

            return self._json_response(404, {"error": "接口不存在。"}, extra_headers=response_headers)
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
    def _json_response(
        status_code: int,
        payload: dict[str, object],
        *,
        extra_headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, str], bytes]:
        headers = {"Content-Type": "application/json; charset=utf-8"}
        if extra_headers:
            headers.update(extra_headers)
        return (
            status_code,
            headers,
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

    @staticmethod
    def _serialize_session_user(context: SproutSessionContext) -> dict[str, object]:
        return {
            "id": context.user_id,
            "email": context.email,
            "user_metadata": context.user_payload.get("user_metadata") or {},
            "app_metadata": context.user_payload.get("app_metadata") or {},
        }

    @staticmethod
    def _collect_auth_headers(session_resolution) -> dict[str, str]:
        headers: dict[str, str] = {}
        if session_resolution.set_cookie_header:
            headers["Set-Cookie"] = session_resolution.set_cookie_header
        if session_resolution.clear_cookie_header:
            headers["Set-Cookie"] = session_resolution.clear_cookie_header
        return headers

    def _ensure_project_action(self, user_id: str, project_id: str, action: str) -> None:
        role = self._get_project_service().get_project_role_for_user(user_id, project_id)
        if not role_has_action(role, action):
            raise PermissionError(f"当前项目角色 {role!r} 无权执行动作 {action!r}。")

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

    def _get_auth_service(self) -> SproutAuthService:
        if self.auth_service is None:
            self.auth_service = SproutAuthService()
        return self.auth_service
