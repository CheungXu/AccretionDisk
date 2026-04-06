"""Sprout 工作流节点定义。"""

from __future__ import annotations

from typing import Any


PROJECT_NODE_KEY = "project"
EMPTY_PROJECT_PLACEHOLDER_NOTE = "sprout:empty_project_placeholder"

NODE_TYPE_LABELS = {
    "user_input": "用户输入",
    "characters": "角色资产",
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


def build_workflow_node_specs(bundle) -> list[dict[str, Any]]:
    """构建线性工作流节点定义。"""

    nodes: list[dict[str, Any]] = [
        {
            "node_id": build_node_id("user_input", PROJECT_NODE_KEY),
            "node_type": "user_input",
            "node_key": PROJECT_NODE_KEY,
            "title": "用户输入",
        },
    ]

    if is_empty_project_placeholder(bundle):
        return nodes

    nodes.extend(
        [
            {
                "node_id": build_node_id("characters", PROJECT_NODE_KEY),
                "node_type": "characters",
                "node_key": PROJECT_NODE_KEY,
                "title": "角色资产",
            }
        ]
    )

    for shot in bundle.shots:
        shot_title = (shot.title or shot.shot_id or "未命名镜头").strip()
        display_title = f"《{shot_title}》"
        nodes.append(
            {
                "node_id": build_node_id("prepare_shot", shot.shot_id),
                "node_type": "prepare_shot",
                "node_key": shot.shot_id,
                "title": f"{display_title}·提示词准备",
            }
        )
        nodes.append(
            {
                "node_id": build_node_id("generate_shot", shot.shot_id),
                "node_type": "generate_shot",
                "node_key": shot.shot_id,
                "title": f"{display_title}·视频生成",
            }
        )

    nodes.extend(
        [
            {
                "node_id": build_node_id("build_cards", PROJECT_NODE_KEY),
                "node_type": "build_cards",
                "node_key": PROJECT_NODE_KEY,
                "title": "执行卡",
            },
            {
                "node_id": build_node_id("export", PROJECT_NODE_KEY),
                "node_type": "export",
                "node_key": PROJECT_NODE_KEY,
                "title": "项目导出",
            },
            {
                "node_id": build_node_id("final_output", PROJECT_NODE_KEY),
                "node_type": "final_output",
                "node_key": PROJECT_NODE_KEY,
                "title": "最终成片",
            },
        ]
    )
    return nodes


def get_upstream_node_ids(bundle, node_type: str, node_key: str) -> list[str]:
    """返回目标节点之前的所有上游节点 ID。"""

    target_node_id = build_node_id(node_type, node_key)
    upstream_node_ids: list[str] = []
    for node in build_workflow_node_specs(bundle):
        if node["node_id"] == target_node_id:
            return upstream_node_ids
        upstream_node_ids.append(node["node_id"])
    raise KeyError(f"未找到节点：{target_node_id}")
