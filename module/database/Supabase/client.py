"""Supabase HTTP 客户端封装。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib import error, parse, request

from .config import (
    coerce_positive_int,
    load_supabase_config,
    load_supabase_secret,
    normalize_optional_str,
)


DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_SCHEMA = "public"
DEFAULT_HEADERS = {
    "X-Client-Info": "AccretionDisk-Supabase/1.0",
}


class SupabaseClientError(RuntimeError):
    """Supabase 客户端异常。"""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        payload: Any = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


@dataclass
class SupabaseRestClient:
    """基于标准库的 Supabase REST 客户端。"""

    url: str
    api_key: str
    schema: str = DEFAULT_SCHEMA
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    default_headers: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.url:
            raise SupabaseClientError("Supabase URL 不能为空。")
        if not self.api_key:
            raise SupabaseClientError("Supabase API Key 不能为空。")
        self.url = self.url.rstrip("/")

    @property
    def auth_base_url(self) -> str:
        """认证接口根地址。"""

        return f"{self.url}/auth/v1"

    @property
    def rest_base_url(self) -> str:
        """REST 接口根地址。"""

        return f"{self.url}/rest/v1"

    @property
    def storage_base_url(self) -> str:
        """Storage 接口根地址。"""

        return f"{self.url}/storage/v1"

    def request_json(
        self,
        method: str,
        path: str,
        *,
        base_path: str = "auth",
        query: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
        bearer_token: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Any:
        """发起 JSON 请求并返回解析结果。"""

        url = self._build_url(path=path, base_path=base_path, query=query)
        headers = self._build_headers(
            base_path=base_path,
            bearer_token=bearer_token,
            extra_headers=extra_headers,
        )
        payload = None
        if body is not None:
            payload = json.dumps(body, ensure_ascii=False).encode("utf-8")

        req = request.Request(url, data=payload, headers=headers, method=method.upper())
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                return self._read_response(response)
        except error.HTTPError as exc:
            details = self._read_error_payload(exc)
            message = self._format_http_error(
                method=method,
                url=url,
                status_code=exc.code,
                payload=details,
            )
            raise SupabaseClientError(message, status_code=exc.code, payload=details) from exc
        except error.URLError as exc:
            raise SupabaseClientError(f"请求 Supabase 失败: {exc.reason}") from exc

    def request_bytes(
        self,
        method: str,
        path: str,
        *,
        base_path: str,
        query: dict[str, Any] | None = None,
        body_bytes: bytes | None = None,
        bearer_token: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> bytes:
        """发起原始字节请求并返回二进制内容。"""

        url = self._build_url(path=path, base_path=base_path, query=query)
        headers = self._build_headers(
            base_path=base_path,
            bearer_token=bearer_token,
            extra_headers=extra_headers,
        )
        req = request.Request(url, data=body_bytes, headers=headers, method=method.upper())
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                return response.read()
        except error.HTTPError as exc:
            details = self._read_error_payload(exc)
            message = self._format_http_error(
                method=method,
                url=url,
                status_code=exc.code,
                payload=details,
            )
            raise SupabaseClientError(message, status_code=exc.code, payload=details) from exc
        except error.URLError as exc:
            raise SupabaseClientError(f"请求 Supabase 失败: {exc.reason}") from exc

    def _build_url(
        self,
        *,
        path: str,
        base_path: str,
        query: dict[str, Any] | None,
    ) -> str:
        normalized_path = path if path.startswith("/") else f"/{path}"
        if base_path == "auth":
            base_url = self.auth_base_url
        elif base_path == "rest":
            base_url = self.rest_base_url
        elif base_path == "storage":
            base_url = self.storage_base_url
        else:
            raise SupabaseClientError(f"不支持的 Supabase 基础路径类型: {base_path}")

        url = f"{base_url}{normalized_path}"
        if query:
            encoded_pairs = []
            for key, value in query.items():
                if value is None:
                    continue
                encoded_pairs.append((key, str(value)))
            if encoded_pairs:
                url = f"{url}?{parse.urlencode(encoded_pairs)}"
        return url

    def _build_headers(
        self,
        *,
        base_path: str,
        bearer_token: str | None,
        extra_headers: dict[str, str] | None,
    ) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "apikey": self.api_key,
        }
        headers.update(DEFAULT_HEADERS)
        headers.update(self.default_headers)

        if base_path == "rest" and self.schema:
            headers["Accept-Profile"] = self.schema
            headers["Content-Profile"] = self.schema

        if bearer_token:
            headers["Authorization"] = f"Bearer {bearer_token}"

        if extra_headers:
            headers.update(extra_headers)
        return headers

    @staticmethod
    def _read_response(response: Any) -> Any:
        raw_body = response.read()
        if not raw_body:
            return {}

        text = raw_body.decode("utf-8")
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"raw_text": text}

    @staticmethod
    def _read_error_payload(exc: error.HTTPError) -> Any:
        raw_body = exc.read()
        if not raw_body:
            return {}

        text = raw_body.decode("utf-8", errors="replace")
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"raw_text": text}

    @staticmethod
    def _format_http_error(
        *,
        method: str,
        url: str,
        status_code: int,
        payload: Any,
    ) -> str:
        message = f"Supabase 请求失败: {method.upper()} {url} -> HTTP {status_code}"
        if isinstance(payload, dict):
            error_message = payload.get("msg") or payload.get("message") or payload.get("error_description")
            if error_message:
                message = f"{message}，{error_message}"
        elif isinstance(payload, list):
            message = f"{message}，返回了列表错误信息"
        return message


@dataclass
class SupabaseClientFactory:
    """Supabase 客户端工厂。"""

    secret_config_path: str | Path | None = None
    params_config_path: str | Path | None = None
    _secret_config: Any = field(init=False, repr=False)
    _params_config: dict[str, Any] = field(init=False, repr=False, default_factory=dict)

    def __post_init__(self) -> None:
        self._secret_config = load_supabase_secret(self.secret_config_path)
        self._params_config = load_supabase_config(self.params_config_path)

    def create_anon_client(
        self,
        *,
        schema: str | None = None,
        timeout_seconds: int | None = None,
        default_headers: dict[str, str] | None = None,
    ) -> SupabaseRestClient:
        """创建使用 anon_key 的客户端。"""

        return self._build_client(
            api_key=self._secret_config.require_anon_key(),
            schema=schema,
            timeout_seconds=timeout_seconds,
            default_headers=default_headers,
        )

    def create_service_client(
        self,
        *,
        schema: str | None = None,
        timeout_seconds: int | None = None,
        default_headers: dict[str, str] | None = None,
    ) -> SupabaseRestClient:
        """创建使用 service_role_key 的客户端。"""

        return self._build_client(
            api_key=self._secret_config.require_service_role_key(),
            schema=schema,
            timeout_seconds=timeout_seconds,
            default_headers=default_headers,
        )

    def _build_client(
        self,
        *,
        api_key: str,
        schema: str | None,
        timeout_seconds: int | None,
        default_headers: dict[str, str] | None,
    ) -> SupabaseRestClient:
        config_schema = normalize_optional_str(self._params_config.get("schema")) or DEFAULT_SCHEMA
        config_timeout = coerce_positive_int(
            self._params_config.get("timeout_seconds"),
            default=DEFAULT_TIMEOUT_SECONDS,
        )
        headers = extract_headers(self._params_config.get("headers"))
        if default_headers:
            headers.update(default_headers)

        return SupabaseRestClient(
            url=self._secret_config.require_url(),
            api_key=api_key,
            schema=schema or config_schema,
            timeout_seconds=timeout_seconds or config_timeout,
            default_headers=headers,
        )


def create_anon_client(
    *,
    secret_config_path: str | Path | None = None,
    params_config_path: str | Path | None = None,
    schema: str | None = None,
    timeout_seconds: int | None = None,
    default_headers: dict[str, str] | None = None,
) -> SupabaseRestClient:
    """快捷创建 anon 客户端。"""

    factory = SupabaseClientFactory(
        secret_config_path=secret_config_path,
        params_config_path=params_config_path,
    )
    return factory.create_anon_client(
        schema=schema,
        timeout_seconds=timeout_seconds,
        default_headers=default_headers,
    )


def create_service_client(
    *,
    secret_config_path: str | Path | None = None,
    params_config_path: str | Path | None = None,
    schema: str | None = None,
    timeout_seconds: int | None = None,
    default_headers: dict[str, str] | None = None,
) -> SupabaseRestClient:
    """快捷创建 service 客户端。"""

    factory = SupabaseClientFactory(
        secret_config_path=secret_config_path,
        params_config_path=params_config_path,
    )
    return factory.create_service_client(
        schema=schema,
        timeout_seconds=timeout_seconds,
        default_headers=default_headers,
    )


def extract_headers(value: Any) -> dict[str, str]:
    """从配置中提取可用的 header。"""

    if not isinstance(value, dict):
        return {}

    headers: dict[str, str] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            continue
        normalized_value = normalize_optional_str(item)
        if normalized_value is None:
            continue
        headers[key] = normalized_value
    return headers
