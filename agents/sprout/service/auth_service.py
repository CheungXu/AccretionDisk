"""Sprout 登录态与 admin 用户服务。"""

from __future__ import annotations

import base64
import json
import secrets
from dataclasses import dataclass
from http import cookies
from typing import Any

from module.database.Supabase import (
    TABLE_PROFILES,
    SupabaseAdminAuthService,
    SupabaseAuthService,
    SupabaseProjectTableService,
    create_admin_auth_service,
    create_auth_service,
    create_project_table_service,
)


SESSION_COOKIE_NAME = "sprout_session"
DEFAULT_SESSION_MAX_AGE_SECONDS = 7 * 24 * 60 * 60
DEFAULT_ADMIN_EMAIL = "sprout-admin@example.com"


@dataclass(frozen=True)
class SproutSessionContext:
    """当前登录用户上下文。"""

    user_id: str
    email: str
    user_payload: dict[str, Any]
    session_payload: dict[str, Any]


@dataclass(frozen=True)
class SproutSessionResolution:
    """登录态解析结果。"""

    context: SproutSessionContext | None
    set_cookie_header: str | None = None
    clear_cookie_header: str | None = None


@dataclass
class SproutAuthService:
    """Sprout 的登录态、Cookie 和 admin 用户管理服务。"""

    auth_service: SupabaseAuthService | None = None
    admin_auth_service: SupabaseAdminAuthService | None = None
    table_service: SupabaseProjectTableService | None = None
    session_cookie_name: str = SESSION_COOKIE_NAME
    session_max_age_seconds: int = DEFAULT_SESSION_MAX_AGE_SECONDS
    secure_cookie: bool = False

    def login_with_password(self, *, email: str, password: str) -> tuple[SproutSessionContext, str]:
        """使用邮箱密码登录，并返回 Cookie。"""

        auth_service = self._build_auth_service()
        auth_service.sign_in_with_password(email=email, password=password)
        session_payload = auth_service.get_current_session()
        if not isinstance(session_payload, dict):
            raise ValueError("登录成功但未拿到 session。")
        user_payload = auth_service.get_current_user()
        context = self._build_context(user_payload, session_payload)
        return context, self.build_session_cookie(session_payload)

    def resolve_session_from_headers(self, headers: dict[str, str] | None) -> SproutSessionResolution:
        """从请求头解析登录态。"""

        session_payload = self._load_session_payload_from_headers(headers)
        if session_payload is None:
            return SproutSessionResolution(context=None)

        auth_service = self._build_auth_service()
        auth_service.restore_session(session_payload)
        try:
            user_payload = auth_service.get_current_user()
        except Exception:
            return SproutSessionResolution(
                context=None,
                clear_cookie_header=self.build_clear_session_cookie(),
            )

        refreshed_session = auth_service.get_current_session() or session_payload
        next_cookie_header = None
        if refreshed_session != session_payload:
            next_cookie_header = self.build_session_cookie(refreshed_session)
        context = self._build_context(user_payload, refreshed_session)
        return SproutSessionResolution(
            context=context,
            set_cookie_header=next_cookie_header,
        )

    def logout_headers(self) -> str:
        """返回清理登录态 Cookie 的响应头。"""

        return self.build_clear_session_cookie()

    def logout_from_headers(self, headers: dict[str, str] | None) -> str:
        """根据当前请求头执行登出，并返回清 Cookie 头。"""

        session_payload = self._load_session_payload_from_headers(headers)
        if isinstance(session_payload, dict):
            auth_service = self._build_auth_service()
            auth_service.restore_session(session_payload)
            try:
                auth_service.sign_out()
            except Exception:
                pass
        return self.build_clear_session_cookie()

    def ensure_admin_user(
        self,
        *,
        email: str = DEFAULT_ADMIN_EMAIL,
        password: str | None = None,
        display_name: str = "Sprout Admin",
    ) -> dict[str, Any]:
        """创建或重置临时 admin 用户。"""

        final_password = password or self.generate_temporary_password()
        admin_service = self._get_admin_auth_service()
        existing_user = admin_service.find_user_by_email(email)
        if existing_user is None:
            response = admin_service.create_user(
                email=email,
                password=final_password,
                email_confirm=True,
                user_metadata={"display_name": display_name},
                app_metadata={"role": "admin", "sprout_role": "admin"},
            )
            user_payload = self._extract_user_from_admin_response(response)
            created = True
        else:
            user_payload = self._extract_user_from_admin_response(
                admin_service.update_user_by_id(
                    existing_user.get("id"),
                    password=final_password,
                    email_confirm=True,
                    user_metadata={
                        **(existing_user.get("user_metadata") or {}),
                        "display_name": display_name,
                    },
                    app_metadata={
                        **(existing_user.get("app_metadata") or {}),
                        "role": "admin",
                        "sprout_role": "admin",
                    },
                )
            )
            created = False

        user_id = str(user_payload.get("id") or "").strip()
        if not user_id:
            raise ValueError("创建 admin 用户后未获取到 user_id。")

        profile_synced = True
        profile_error = None
        try:
            self._upsert_profile(
                {
                    "id": user_id,
                    "display_name": display_name,
                    "email": user_payload.get("email") or email,
                    "avatar_url": None,
                }
            )
        except Exception as exc:
            profile_synced = False
            profile_error = str(exc)

        return {
            "created": created,
            "email": email,
            "password": final_password,
            "user": user_payload,
            "profile_synced": profile_synced,
            "profile_error": profile_error,
        }

    def build_session_cookie(self, session_payload: dict[str, Any]) -> str:
        """构造 session Cookie。"""

        encoded_value = self._encode_session_cookie_value(session_payload)
        cookie = cookies.SimpleCookie()
        cookie[self.session_cookie_name] = encoded_value
        morsel = cookie[self.session_cookie_name]
        morsel["path"] = "/"
        morsel["httponly"] = True
        morsel["samesite"] = "Lax"
        morsel["max-age"] = str(self.session_max_age_seconds)
        if self.secure_cookie:
            morsel["secure"] = True
        return morsel.OutputString()

    def build_clear_session_cookie(self) -> str:
        """构造清理 session 的 Cookie。"""

        cookie = cookies.SimpleCookie()
        cookie[self.session_cookie_name] = ""
        morsel = cookie[self.session_cookie_name]
        morsel["path"] = "/"
        morsel["httponly"] = True
        morsel["samesite"] = "Lax"
        morsel["max-age"] = "0"
        if self.secure_cookie:
            morsel["secure"] = True
        return morsel.OutputString()

    @staticmethod
    def generate_temporary_password() -> str:
        """生成临时强密码。"""

        return f"Tmp-{secrets.token_urlsafe(12)}A1!"

    def _build_context(self, user_payload: dict[str, Any], session_payload: dict[str, Any]) -> SproutSessionContext:
        user_id = str(user_payload.get("id") or "").strip()
        email = str(user_payload.get("email") or "").strip()
        if not user_id or not email:
            raise ValueError("当前用户信息不完整。")
        return SproutSessionContext(
            user_id=user_id,
            email=email,
            user_payload=user_payload,
            session_payload=session_payload,
        )

    def _load_session_payload_from_headers(self, headers: dict[str, str] | None) -> dict[str, Any] | None:
        cookie_header = read_header(headers, "Cookie")
        if not cookie_header:
            return None
        cookie = cookies.SimpleCookie()
        cookie.load(cookie_header)
        morsel = cookie.get(self.session_cookie_name)
        if morsel is None:
            return None
        return self._decode_session_cookie_value(morsel.value)

    @staticmethod
    def _encode_session_cookie_value(session_payload: dict[str, Any]) -> str:
        serialized = json.dumps(session_payload, ensure_ascii=False, separators=(",", ":"))
        return base64.urlsafe_b64encode(serialized.encode("utf-8")).decode("ascii")

    @staticmethod
    def _decode_session_cookie_value(cookie_value: str) -> dict[str, Any] | None:
        try:
            raw_bytes = base64.urlsafe_b64decode(cookie_value.encode("ascii"))
            payload = json.loads(raw_bytes.decode("utf-8"))
        except Exception:
            return None
        return payload if isinstance(payload, dict) else None

    def _extract_user_from_admin_response(self, response: dict[str, Any]) -> dict[str, Any]:
        user_payload = response.get("user")
        if isinstance(user_payload, dict):
            return user_payload
        if response.get("id"):
            return response
        raise ValueError("admin 接口返回中未包含 user 信息。")

    def _upsert_profile(self, row: dict[str, Any]) -> None:
        self._get_table_service().upsert_rows(TABLE_PROFILES, row, on_conflict=("id",))

    def _build_auth_service(self) -> SupabaseAuthService:
        auth_service = self.auth_service or create_auth_service(
            persist_session=True,
            auto_refresh_token=True,
        )
        auth_service.clear_session()
        return auth_service

    def _get_admin_auth_service(self) -> SupabaseAdminAuthService:
        if self.admin_auth_service is None:
            self.admin_auth_service = create_admin_auth_service()
        return self.admin_auth_service

    def _get_table_service(self) -> SupabaseProjectTableService:
        if self.table_service is None:
            self.table_service = create_project_table_service()
        return self.table_service


def read_header(headers: dict[str, str] | None, name: str) -> str | None:
    """大小写不敏感读取请求头。"""

    if not headers:
        return None
    target_name = name.lower()
    for key, value in headers.items():
        if key.lower() == target_name:
            return value
    return None
