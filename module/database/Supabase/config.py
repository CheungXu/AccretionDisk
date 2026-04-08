"""Supabase 配置读取工具。"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT_PATH = Path(__file__).resolve().parents[3]
DEFAULT_SECRET_CONFIG_PATH = ROOT_PATH / "config" / "supabase_key.json"
DEFAULT_PARAMS_CONFIG_PATH = ROOT_PATH / "config" / "supabase_config.json"


@dataclass(frozen=True)
class SupabaseSecretConfig:
    """Supabase 敏感配置。"""

    url: str | None = None
    anon_key: str | None = None
    service_role_key: str | None = None

    def require_url(self) -> str:
        """获取必填的项目地址。"""

        if not self.url:
            raise ValueError("缺少 Supabase URL，请先填写 config/supabase_key.json 或设置 SUPABASE_URL。")
        return self.url

    def require_anon_key(self) -> str:
        """获取必填的匿名访问密钥。"""

        if not self.anon_key:
            raise ValueError(
                "缺少 Supabase anon_key，请先填写 config/supabase_key.json 或设置 SUPABASE_ANON_KEY。"
            )
        return self.anon_key

    def require_service_role_key(self) -> str:
        """获取必填的服务端管理密钥。"""

        if not self.service_role_key:
            raise ValueError(
                "缺少 Supabase service_role_key，请先填写 config/supabase_key.json 或设置 SUPABASE_SERVICE_ROLE_KEY。"
            )
        return self.service_role_key


@dataclass(frozen=True)
class SupabaseStorageConfig:
    """Supabase Storage 公共配置。"""

    bucket_name: str = "sprout-projects"
    path_prefix: str = "projects"
    signed_url_ttl_seconds: int = 3600
    public_bucket: bool = False

    def build_prefixed_path(self, *parts: str) -> str:
        """基于路径前缀拼接对象路径。"""

        normalized_parts = [self.path_prefix, *parts]
        return "/".join(
            normalize_path_segment(segment)
            for segment in normalized_parts
            if normalize_path_segment(segment)
        )


def load_supabase_secret(
    secret_config_path: str | Path | None = None,
) -> SupabaseSecretConfig:
    """优先从环境变量读取敏感参数，其次读取本地密钥配置。"""

    config_path = Path(secret_config_path) if secret_config_path else DEFAULT_SECRET_CONFIG_PATH
    file_config = load_json_file(config_path) if config_path.exists() else {}

    return SupabaseSecretConfig(
        url=normalize_optional_str(os.getenv("SUPABASE_URL")) or normalize_optional_str(file_config.get("url")),
        anon_key=normalize_optional_str(os.getenv("SUPABASE_ANON_KEY"))
        or normalize_optional_str(file_config.get("anon_key")),
        service_role_key=normalize_optional_str(os.getenv("SUPABASE_SERVICE_ROLE_KEY"))
        or normalize_optional_str(file_config.get("service_role_key")),
    )


def load_supabase_config(
    params_config_path: str | Path | None = None,
) -> dict[str, Any]:
    """读取 Supabase 公共配置。"""

    config_path = Path(params_config_path) if params_config_path else DEFAULT_PARAMS_CONFIG_PATH
    if not config_path.exists():
        return {}
    return load_json_file(config_path)


def load_supabase_section(
    section_name: str,
    params_config_path: str | Path | None = None,
) -> dict[str, Any]:
    """读取 Supabase 公共配置中的某个分组。"""

    config = load_supabase_config(params_config_path)
    section = config.get(section_name, {})
    if not isinstance(section, dict):
        raise ValueError(f"Supabase 配置分组格式错误: {section_name}")
    return section


def load_supabase_storage_config(
    params_config_path: str | Path | None = None,
) -> SupabaseStorageConfig:
    """读取 Supabase Storage 配置。"""

    storage_config = load_supabase_section("storage", params_config_path)
    return SupabaseStorageConfig(
        bucket_name=normalize_optional_str(storage_config.get("bucket_name")) or "sprout-projects",
        path_prefix=normalize_optional_str(storage_config.get("path_prefix")) or "projects",
        signed_url_ttl_seconds=coerce_positive_int(
            storage_config.get("signed_url_ttl_seconds"),
            default=3600,
        ),
        public_bucket=coerce_bool(storage_config.get("public_bucket"), default=False),
    )


def load_json_file(config_path: str | Path) -> dict[str, Any]:
    """读取 JSON 配置文件。"""

    path = Path(config_path)
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise OSError(f"读取配置文件失败: {path}") from exc

    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise json.JSONDecodeError(f"配置文件不是合法 JSON: {path}", content, exc.pos) from exc

    if not isinstance(data, dict):
        raise ValueError(f"配置文件顶层必须为对象: {path}")
    return data


def normalize_optional_str(value: Any) -> str | None:
    """将字符串配置归一化，模板占位内容按未配置处理。"""

    if not isinstance(value, str):
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if normalized.startswith("请填写"):
        return None
    return normalized


def normalize_path_segment(value: Any) -> str:
    """将对象路径片段归一化。"""

    if value is None:
        return ""
    normalized = str(value).strip().replace("\\", "/")
    normalized = normalized.strip("/")
    return normalized


def coerce_positive_int(value: Any, *, default: int) -> int:
    """将配置值转成正整数。"""

    if isinstance(value, bool):
        return default
    if isinstance(value, int) and value > 0:
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.isdigit():
            parsed = int(stripped)
            if parsed > 0:
                return parsed
    return default


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
