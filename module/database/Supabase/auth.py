"""Supabase 认证能力封装。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib import parse

from .client import SupabaseClientError, SupabaseClientFactory, SupabaseRestClient
from .config import load_supabase_section, normalize_optional_str


class SupabaseAuthError(RuntimeError):
    """Supabase 认证异常。"""


@dataclass
class SupabaseAuthService:
    """面向普通用户侧的认证服务。"""

    client: SupabaseRestClient
    persist_session: bool = True
    auto_refresh_token: bool = True
    default_email_redirect_to: str | None = None
    _session: dict[str, Any] | None = field(default=None, init=False, repr=False)

    def sign_up(
        self,
        *,
        email: str,
        password: str,
        metadata: dict[str, Any] | None = None,
        email_redirect_to: str | None = None,
    ) -> dict[str, Any]:
        """使用邮箱密码注册用户。"""

        payload: dict[str, Any] = {
            "email": email,
            "password": password,
        }
        options: dict[str, Any] = {}
        if metadata:
            options["data"] = metadata

        redirect_to = normalize_optional_str(email_redirect_to) or self.default_email_redirect_to
        if redirect_to:
            options["email_redirect_to"] = redirect_to

        if options:
            payload["options"] = options

        response = self.client.request_json("POST", "/signup", body=payload)
        self._store_session_from_response(response)
        return ensure_dict_response(response, action_name="注册")

    def sign_in_with_password(
        self,
        *,
        email: str,
        password: str,
    ) -> dict[str, Any]:
        """使用邮箱密码登录。"""

        response = self.client.request_json(
            "POST",
            "/token",
            query={"grant_type": "password"},
            body={"email": email, "password": password},
        )
        self._store_session_from_response(response)
        return ensure_dict_response(response, action_name="登录")

    def sign_out(
        self,
        *,
        access_token: str | None = None,
        scope: str = "global",
    ) -> dict[str, Any]:
        """退出登录并清理本地 session。"""

        token = self._resolve_access_token(access_token)
        response = self.client.request_json(
            "POST",
            "/logout",
            query={"scope": scope},
            bearer_token=token,
        )
        self.clear_session()
        return ensure_dict_response(response, action_name="登出")

    def refresh_session(
        self,
        *,
        refresh_token: str | None = None,
    ) -> dict[str, Any]:
        """刷新访问会话。"""

        token = normalize_optional_str(refresh_token) or self.get_refresh_token()
        if not token:
            raise SupabaseAuthError("缺少 refresh_token，无法刷新 session。")

        response = self.client.request_json(
            "POST",
            "/token",
            query={"grant_type": "refresh_token"},
            body={"refresh_token": token},
        )
        self._store_session_from_response(response)
        return ensure_dict_response(response, action_name="刷新 session")

    def get_current_user(
        self,
        *,
        access_token: str | None = None,
    ) -> dict[str, Any]:
        """获取当前登录用户。"""

        token = self._resolve_access_token(access_token)
        response = self.client.request_json("GET", "/user", bearer_token=token)
        return ensure_dict_response(response, action_name="获取当前用户")

    def get_current_session(self) -> dict[str, Any] | None:
        """返回当前内存中的 session。"""

        if self._session is None:
            return None
        return dict(self._session)

    def get_access_token(self) -> str | None:
        """读取当前 access_token。"""

        if not self._session:
            return None
        return normalize_optional_str(self._session.get("access_token"))

    def get_refresh_token(self) -> str | None:
        """读取当前 refresh_token。"""

        if not self._session:
            return None
        return normalize_optional_str(self._session.get("refresh_token"))

    def clear_session(self) -> None:
        """清理当前进程内保存的 session。"""

        self._session = None

    def restore_session(self, session_payload: dict[str, Any] | None) -> None:
        """从外部恢复 session。"""

        if not isinstance(session_payload, dict):
            self._session = None
            return
        self._session = dict(session_payload)

    def _resolve_access_token(self, access_token: str | None) -> str:
        token = normalize_optional_str(access_token) or self.get_access_token()
        if token:
            return token

        if self.auto_refresh_token and self.get_refresh_token():
            self.refresh_session()
            refreshed_token = self.get_access_token()
            if refreshed_token:
                return refreshed_token

        raise SupabaseAuthError("缺少 access_token，请先登录，或显式传入 access_token。")

    def _store_session_from_response(self, response: Any) -> None:
        if not self.persist_session:
            return
        if not isinstance(response, dict):
            return

        session = response.get("session")
        if isinstance(session, dict):
            self._session = dict(session)
            return

        access_token = normalize_optional_str(response.get("access_token"))
        refresh_token = normalize_optional_str(response.get("refresh_token"))
        if access_token and refresh_token:
            self._session = {
                "access_token": access_token,
                "refresh_token": refresh_token,
            }


@dataclass
class SupabaseAdminAuthService:
    """面向服务端管理任务的认证服务。"""

    client: SupabaseRestClient

    @property
    def service_bearer_token(self) -> str:
        """返回管理侧接口所需的服务端 Bearer Token。"""

        return self.client.api_key

    def list_users(
        self,
        *,
        page: int | None = None,
        per_page: int | None = None,
    ) -> dict[str, Any]:
        """分页查询用户列表。"""

        response = self.client.request_json(
            "GET",
            "/admin/users",
            query={"page": page, "per_page": per_page},
            bearer_token=self.service_bearer_token,
        )
        return ensure_dict_response(response, action_name="查询用户列表")

    def get_user(self, user_id: str) -> dict[str, Any]:
        """根据用户 ID 查询单个用户。"""

        normalized_user_id = normalize_optional_str(user_id)
        if not normalized_user_id:
            raise SupabaseAuthError("user_id 不能为空。")

        quoted_user_id = parse.quote(normalized_user_id, safe="")
        response = self.client.request_json(
            "GET",
            f"/admin/users/{quoted_user_id}",
            bearer_token=self.service_bearer_token,
        )
        return ensure_dict_response(response, action_name="查询单个用户")

    def create_user(
        self,
        *,
        email: str,
        password: str,
        email_confirm: bool = True,
        user_metadata: dict[str, Any] | None = None,
        app_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """创建用户。"""

        payload: dict[str, Any] = {
            "email": email,
            "password": password,
            "email_confirm": email_confirm,
        }
        if user_metadata:
            payload["user_metadata"] = user_metadata
        if app_metadata:
            payload["app_metadata"] = app_metadata
        response = self.client.request_json(
            "POST",
            "/admin/users",
            bearer_token=self.service_bearer_token,
            body=payload,
        )
        return ensure_dict_response(response, action_name="创建用户")

    def find_user_by_email(self, email: str, *, per_page: int = 50, max_pages: int = 20) -> dict[str, Any] | None:
        """按邮箱查找用户。"""

        normalized_email = normalize_optional_str(email)
        if not normalized_email:
            raise SupabaseAuthError("email 不能为空。")

        for page in range(1, max_pages + 1):
            response = self.list_users(page=page, per_page=per_page)
            users = response.get("users")
            if not isinstance(users, list) or not users:
                return None
            for item in users:
                if not isinstance(item, dict):
                    continue
                user_email = normalize_optional_str(item.get("email"))
                if user_email and user_email.lower() == normalized_email.lower():
                    return item
            if len(users) < per_page:
                return None
        return None

    def update_user_by_id(
        self,
        user_id: str,
        *,
        email: str | None = None,
        password: str | None = None,
        email_confirm: bool | None = None,
        user_metadata: dict[str, Any] | None = None,
        app_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """按 ID 更新用户。"""

        normalized_user_id = normalize_optional_str(user_id)
        if not normalized_user_id:
            raise SupabaseAuthError("user_id 不能为空。")

        payload: dict[str, Any] = {}
        if normalize_optional_str(email):
            payload["email"] = normalize_optional_str(email)
        if normalize_optional_str(password):
            payload["password"] = normalize_optional_str(password)
        if email_confirm is not None:
            payload["email_confirm"] = email_confirm
        if user_metadata:
            payload["user_metadata"] = user_metadata
        if app_metadata:
            payload["app_metadata"] = app_metadata
        if not payload:
            raise SupabaseAuthError("至少需要提供一个更新字段。")

        quoted_user_id = parse.quote(normalized_user_id, safe="")
        response = self.client.request_json(
            "PUT",
            f"/admin/users/{quoted_user_id}",
            bearer_token=self.service_bearer_token,
            body=payload,
        )
        return ensure_dict_response(response, action_name="更新用户")


def create_auth_service(
    *,
    secret_config_path: str | Path | None = None,
    params_config_path: str | Path | None = None,
    persist_session: bool | None = None,
    auto_refresh_token: bool | None = None,
    default_email_redirect_to: str | None = None,
) -> SupabaseAuthService:
    """根据本地配置创建普通认证服务。"""

    factory = SupabaseClientFactory(
        secret_config_path=secret_config_path,
        params_config_path=params_config_path,
    )
    auth_config = load_supabase_section("auth", params_config_path)
    return SupabaseAuthService(
        client=factory.create_anon_client(),
        persist_session=coerce_bool(auth_config.get("persist_session"), default=True)
        if persist_session is None
        else persist_session,
        auto_refresh_token=coerce_bool(auth_config.get("auto_refresh_token"), default=True)
        if auto_refresh_token is None
        else auto_refresh_token,
        default_email_redirect_to=normalize_optional_str(default_email_redirect_to)
        or normalize_optional_str(auth_config.get("default_email_redirect_to")),
    )


def create_admin_auth_service(
    *,
    secret_config_path: str | Path | None = None,
    params_config_path: str | Path | None = None,
) -> SupabaseAdminAuthService:
    """根据本地配置创建管理侧认证服务。"""

    factory = SupabaseClientFactory(
        secret_config_path=secret_config_path,
        params_config_path=params_config_path,
    )
    return SupabaseAdminAuthService(client=factory.create_service_client())


def ensure_dict_response(response: Any, *, action_name: str) -> dict[str, Any]:
    """确保上游返回字典结构。"""

    if isinstance(response, dict):
        return response
    raise SupabaseClientError(f"{action_name}失败，Supabase 返回了非字典结构。", payload=response)


def coerce_bool(value: Any, *, default: bool) -> bool:
    """将配置值转成布尔值。"""

    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
    return default
