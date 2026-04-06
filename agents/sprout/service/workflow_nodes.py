"""Sprout 工作流节点定义。"""

from __future__ import annotations

from typing import Any


PROJECT_NODE_KEY = "project"
SCRIPT_STORYBOARD_NODE_TYPE = "script_storyboard"
EMPTY_PROJECT_PLACEHOLDER_NOTE = "sprout:empty_project_placeholder"

NODE_TYPE_LABELS = {
    "user_input": "用户输入",
    "characters": "角色资产",
    SCRIPT_STORYBOARD_NODE_TYPE: "脚本分镜",
    "prepare_shot": "提示词准备",
    "generate_shot": "视频生成",
    "build_cards": "执行卡",
    "export": "项目导出",
    "final_output": "最终成片",
}


def build_node_id(node_type: str, node_key: str) -> str:
    """返回标准节点 ID。"""

    return f"{node_type}:{node_key}"


def get_node_type_label(node_type: str) -> str:
    """返回节点类型中文名。"""

    return NODE_TYPE_LABELS.get(node_type, node_type)


def is_empty_project_placeholder(bundle) -> bool:
    """判断当前 bundle 是否为空项目占位状态。"""

    return EMPTY_PROJECT_PLACEHOLDER_NOTE in getattr(bundle, "notes", [])


def _build_node_spec(
    *,
    node_type: str,
    node_key: str,
    title: str,
    upstream_node_ids: list[str] | None = None,
    version_source_node_id: str | None = None,
    visual_parent_node_id: str | None = None,
) -> dict[str, Any]:
    node_id = build_node_id(node_type, node_key)
    return {
        "node_id": node_id,
        "node_type": node_type,
        "node_key": node_key,
        "title": title,
        "upstream_node_ids": list(upstream_node_ids or []),
        "version_source_node_id": version_source_node_id or node_id,
        "visual_parent_node_id": visual_parent_node_id,
    }


def build_workflow_node_specs(bundle) -> list[dict[str, Any]]:
    """构建工作流节点定义。"""

    user_input_node_id = build_node_id("user_input", PROJECT_NODE_KEY)
    nodes: list[dict[str, Any]] = [
        _build_node_spec(
            node_type="user_input",
            node_key=PROJECT_NODE_KEY,
            title="用户输入",
        )
    ]

    if is_empty_project_placeholder(bundle):
        return nodes

    character_node_id = build_node_id("characters", PROJECT_NODE_KEY)
    nodes.extend(
        [
            _build_node_spec(
                node_type="characters",
                node_key=PROJECT_NODE_KEY,
                title="角色资产",
                upstream_node_ids=[user_input_node_id],
            ),
            _build_node_spec(
                node_type=SCRIPT_STORYBOARD_NODE_TYPE,
                node_key=PROJECT_NODE_KEY,
                title="脚本分镜",
                version_source_node_id=user_input_node_id,
                visual_parent_node_id=user_input_node_id,
            ),
        ]
    )

    last_main_node_id = character_node_id
    for shot in bundle.shots:
        shot_title = (shot.title or shot.shot_id or "未命名镜头").strip()
        display_title = f"《{shot_title}》"
        prepare_node_id = build_node_id("prepare_shot", shot.shot_id)
        nodes.append(
            _build_node_spec(
                node_type="prepare_shot",
                node_key=shot.shot_id,
                title=f"{display_title}·提示词准备",
                upstream_node_ids=[last_main_node_id],
            )
        )
        nodes.append(
            _build_node_spec(
                node_type="generate_shot",
                node_key=shot.shot_id,
                title=f"{display_title}·视频生成",
                upstream_node_ids=[prepare_node_id],
            )
        )
        last_main_node_id = build_node_id("generate_shot", shot.shot_id)

    nodes.extend(
        [
            _build_node_spec(
                node_type="build_cards",
                node_key=PROJECT_NODE_KEY,
                title="执行卡",
                upstream_node_ids=[last_main_node_id],
            ),
            _build_node_spec(
                node_type="export",
                node_key=PROJECT_NODE_KEY,
                title="项目导出",
                upstream_node_ids=[build_node_id("build_cards", PROJECT_NODE_KEY)],
            ),
            _build_node_spec(
                node_type="final_output",
                node_key=PROJECT_NODE_KEY,
                title="最终成片",
                upstream_node_ids=[build_node_id("export", PROJECT_NODE_KEY)],
            ),
        ]
    )
    return nodes


def get_node_spec(bundle, node_type: str, node_key: str) -> dict[str, Any]:
    """返回指定节点定义。"""

    target_node_id = build_node_id(node_type, node_key)
    for node_spec in build_workflow_node_specs(bundle):
        if node_spec["node_id"] == target_node_id:
            return node_spec
    raise KeyError(f"未找到节点：{target_node_id}")


def get_upstream_node_ids(bundle, node_type: str, node_key: str) -> list[str]:
    """返回目标节点的所有祖先节点 ID。"""

    target_node_id = build_node_id(node_type, node_key)
    node_specs = build_workflow_node_specs(bundle)
    spec_by_node_id = {node_spec["node_id"]: node_spec for node_spec in node_specs}
    if target_node_id not in spec_by_node_id:
        raise KeyError(f"未找到节点：{target_node_id}")

    upstream_node_ids: list[str] = []
    visited_node_ids: set[str] = set()

    def _collect(current_node_id: str) -> None:
        current_spec = spec_by_node_id[current_node_id]
        for upstream_node_id in current_spec.get("upstream_node_ids", []):
            if upstream_node_id in visited_node_ids:
                continue
            if upstream_node_id not in spec_by_node_id:
                continue
            _collect(upstream_node_id)
            visited_node_ids.add(upstream_node_id)
            upstream_node_ids.append(upstream_node_id)

    _collect(target_node_id)
    return upstream_node_ids
