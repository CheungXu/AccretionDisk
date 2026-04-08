"""Supabase 项目级最小角色模型。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


PROJECT_ROLE_OWNER = "owner"
PROJECT_ROLE_EDITOR = "editor"
PROJECT_ROLE_VIEWER = "viewer"

PROJECT_ACTION_READ = "project.read"
PROJECT_ACTION_UPDATE = "project.update"
PROJECT_ACTION_DELETE = "project.delete"
PROJECT_ACTION_MEMBER_MANAGE = "member.manage"
PROJECT_ACTION_VERSION_ACTIVATE = "version.activate"
PROJECT_ACTION_RUN_RETRY = "run.retry"
PROJECT_ACTION_ASSET_UPLOAD = "asset.upload"
PROJECT_ACTION_ASSET_DELETE = "asset.delete"

ALL_PROJECT_ROLES = (
    PROJECT_ROLE_OWNER,
    PROJECT_ROLE_EDITOR,
    PROJECT_ROLE_VIEWER,
)

ALL_PROJECT_ACTIONS = (
    PROJECT_ACTION_READ,
    PROJECT_ACTION_UPDATE,
    PROJECT_ACTION_DELETE,
    PROJECT_ACTION_MEMBER_MANAGE,
    PROJECT_ACTION_VERSION_ACTIVATE,
    PROJECT_ACTION_RUN_RETRY,
    PROJECT_ACTION_ASSET_UPLOAD,
    PROJECT_ACTION_ASSET_DELETE,
)

PROJECT_ROLE_ACTIONS: dict[str, set[str]] = {
    PROJECT_ROLE_OWNER: set(ALL_PROJECT_ACTIONS),
    PROJECT_ROLE_EDITOR: {
        PROJECT_ACTION_READ,
        PROJECT_ACTION_UPDATE,
        PROJECT_ACTION_RUN_RETRY,
        PROJECT_ACTION_ASSET_UPLOAD,
    },
    PROJECT_ROLE_VIEWER: {
        PROJECT_ACTION_READ,
    },
}


@dataclass(frozen=True)
class ProjectRoleCapability:
    """项目角色能力快照。"""

    role: str
    actions: tuple[str, ...]


class SupabaseAuthorizationError(RuntimeError):
    """Supabase 权限模型异常。"""


def normalize_project_role(role: Any) -> str:
    """归一化项目角色。"""

    normalized_role = str(role or "").strip().lower()
    if normalized_role not in PROJECT_ROLE_ACTIONS:
        raise SupabaseAuthorizationError(f"不支持的项目角色：{role}")
    return normalized_role


def is_valid_project_role(role: Any) -> bool:
    """判断角色是否有效。"""

    try:
        normalize_project_role(role)
    except SupabaseAuthorizationError:
        return False
    return True


def get_actions_for_role(role: Any) -> tuple[str, ...]:
    """返回某个角色的全部动作。"""

    normalized_role = normalize_project_role(role)
    return tuple(sorted(PROJECT_ROLE_ACTIONS[normalized_role]))


def role_has_action(role: Any, action: str) -> bool:
    """判断角色是否拥有某个动作。"""

    normalized_role = normalize_project_role(role)
    normalized_action = normalize_project_action(action)
    return normalized_action in PROJECT_ROLE_ACTIONS[normalized_role]


def ensure_role_has_action(role: Any, action: str) -> None:
    """确保角色拥有指定动作。"""

    if not role_has_action(role, action):
        raise SupabaseAuthorizationError(f"角色 {role!r} 无权执行动作 {action!r}")


def normalize_project_action(action: Any) -> str:
    """归一化项目动作语义。"""

    normalized_action = str(action or "").strip().lower()
    if normalized_action not in ALL_PROJECT_ACTIONS:
        raise SupabaseAuthorizationError(f"不支持的项目动作：{action}")
    return normalized_action


def get_minimum_role_for_action(action: str) -> str:
    """返回某个动作所需的最小角色。"""

    normalized_action = normalize_project_action(action)
    for role in (PROJECT_ROLE_VIEWER, PROJECT_ROLE_EDITOR, PROJECT_ROLE_OWNER):
        if normalized_action in PROJECT_ROLE_ACTIONS[role]:
            return role
    raise SupabaseAuthorizationError(f"未找到动作 {action!r} 对应的最小角色")


def build_role_capability_report() -> list[ProjectRoleCapability]:
    """生成角色能力清单。"""

    return [
        ProjectRoleCapability(role=role, actions=get_actions_for_role(role))
        for role in ALL_PROJECT_ROLES
    ]
