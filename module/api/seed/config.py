"""Seed 配置读取工具。"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


ROOT_PATH = Path(__file__).resolve().parents[3]
DEFAULT_SECRET_CONFIG_PATH = ROOT_PATH / "config" / "seed_key.json"
DEFAULT_PARAMS_CONFIG_PATH = ROOT_PATH / "config" / "seed_config.json"


def load_api_key(secret_config_path: str | Path | None = None) -> str | None:
    """优先从环境变量读取 API Key，其次读取本地密钥配置。"""

    env_api_key = os.getenv("ARK_API_KEY")
    if env_api_key:
        return env_api_key

    config_path = Path(secret_config_path) if secret_config_path else DEFAULT_SECRET_CONFIG_PATH
    if not config_path.exists():
        return None

    config = load_json_file(config_path)
    api_key = config.get("api_key")
    if isinstance(api_key, str) and api_key.strip():
        return api_key.strip()
    return None


def load_seed_section(
    section_name: str,
    params_config_path: str | Path | None = None,
) -> dict[str, Any]:
    """读取 Seed 公共参数配置中的某个模块分组。"""

    config_path = Path(params_config_path) if params_config_path else DEFAULT_PARAMS_CONFIG_PATH
    if not config_path.exists():
        return {}

    config = load_json_file(config_path)
    section = config.get(section_name, {})
    if not isinstance(section, dict):
        raise ValueError(f"配置分组格式错误: {section_name}")
    return section


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
