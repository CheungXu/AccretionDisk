"""基于项目文件结构推断节点版本。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..core.final_output import get_existing_final_video_path
from .types import SproutNodeVersionRecord
from .workflow_nodes import (
    PROJECT_NODE_KEY,
    SCRIPT_STORYBOARD_NODE_TYPE,
    build_node_id,
    build_workflow_node_specs,
    is_empty_project_placeholder,
)


@dataclass
class _NodeMaterial:
    """节点当前文件物料。"""

    has_version: bool
    is_complete: bool
    created_at: str | None
    relevant_paths: list[Path]


def infer_versions_from_project_files(
    *,
    project_root: str | Path,
    project_id: str,
    bundle,
    bundle_path: str | Path,
) -> list[SproutNodeVersionRecord]:
    """根据项目目录结构与文件命名推断当前版本。"""

    root = Path(project_root).expanduser()
    resolved_bundle_path = Path(bundle_path).expanduser()
    completed_version_ids: dict[str, str] = {}
    inferred_versions: list[SproutNodeVersionRecord] = []
    previous_node_state: dict[str, Any] | None = None

    for node_spec in build_workflow_node_specs(bundle):
        node_type = node_spec["node_type"]
        node_key = node_spec["node_key"]

        material = _collect_node_material(
            root=root,
            bundle=bundle,
            bundle_path=resolved_bundle_path,
            node_type=node_type,
            node_key=node_key,
        )
        if not material.has_version or material.created_at is None:
            continue

        created_at = _parse_iso_datetime(material.created_at)
        is_current_complete = material.is_complete
        if previous_node_state is not None and not previous_node_state["is_current_complete"]:
            is_current_complete = False

        dependency_version_ids = dict(completed_version_ids) if is_current_complete else {}
        source_version_id = (
            previous_node_state["version_id"] if is_current_complete and previous_node_state else None
        )
        version_id = _build_inferred_version_id(
            node_type=node_type,
            node_key=node_key,
            created_at=created_at,
        )

        inferred_versions.append(
            SproutNodeVersionRecord(
                version_id=version_id,
                project_id=project_id,
                node_type=node_type,
                node_key=node_key,
                bundle_snapshot_path=str(resolved_bundle_path),
                source_version_id=source_version_id,
                status="ready" if is_current_complete else "stale",
                created_at=material.created_at,
                dependency_version_ids=dependency_version_ids,
                notes=[
                    "source=filesystem",
                    f"complete={str(is_current_complete).lower()}",
                    *[f"path={path.name}" for path in material.relevant_paths[:6]],
                ],
            )
        )

        if is_current_complete:
            completed_version_ids[build_node_id(node_type, node_key)] = version_id

        previous_node_state = {
            "node_id": build_node_id(node_type, node_key),
            "version_id": version_id,
            "created_at": created_at,
            "is_current_complete": is_current_complete,
        }

    return inferred_versions


def build_active_state_from_versions(versions: list[SproutNodeVersionRecord]) -> dict[str, Any]:
    """根据推断出的版本记录生成当前激活状态。"""

    if not versions:
        return {
            "active_bundle_version_id": None,
            "active_bundle_snapshot_path": None,
            "selected_versions": {},
            "updated_at": None,
        }

    latest_version = max(versions, key=lambda item: item.created_at)
    return {
        "active_bundle_version_id": latest_version.version_id,
        "active_bundle_snapshot_path": latest_version.bundle_snapshot_path,
        "selected_versions": {
            build_node_id(version.node_type, version.node_key): version.version_id
            for version in versions
        },
        "updated_at": latest_version.created_at,
    }


def _collect_node_material(
    *,
    root: Path,
    bundle,
    bundle_path: Path,
    node_type: str,
    node_key: str,
) -> _NodeMaterial:
    if node_type == SCRIPT_STORYBOARD_NODE_TYPE:
        return _NodeMaterial(has_version=False, is_complete=False, created_at=None, relevant_paths=[])

    if node_type == "user_input":
        user_input_complete = _has_user_input_content(bundle) or not is_empty_project_placeholder(bundle)
        if is_empty_project_placeholder(bundle) and not user_input_complete:
            return _NodeMaterial(has_version=False, is_complete=False, created_at=None, relevant_paths=[])
        relevant_paths = _glob_existing_files(root / "input", "*_topic_input.json")
        relevant_paths.extend(_glob_existing_files(root / "input", "*_storyboard.txt"))
        if not relevant_paths and bundle_path.exists():
            relevant_paths = [bundle_path]
        return _build_material(relevant_paths, is_complete=user_input_complete)

    if node_type == "characters":
        relevant_paths = _collect_existing_paths(
            [Path(asset.path) for character in bundle.characters for asset in character.reference_assets if asset.path]
        )
        if not relevant_paths:
            relevant_paths = _glob_existing_files(root / "characters", "**/*")
        is_complete = bool(bundle.characters) and all(
            any(asset.path and Path(asset.path).exists() for asset in character.reference_assets)
            for character in bundle.characters
        )
        return _build_material(relevant_paths, is_complete=is_complete)

    if node_type == "build_cards":
        relevant_paths = _glob_existing_files(root / "workflow_cards", "*.md")
        expected_card_count = len(bundle.shots)
        is_complete = expected_card_count > 0 and len(relevant_paths) >= expected_card_count
        return _build_material(relevant_paths, is_complete=is_complete)

    if node_type == "export":
        relevant_paths = _glob_existing_files(root / "manifest", "*_manifest.json")
        relevant_paths.extend(_glob_existing_files(root / "manifest", "*_summary.md"))
        is_complete = bool(relevant_paths) and bool(bundle.manifest and bundle.manifest.status == "ready")
        return _build_material(relevant_paths, is_complete=is_complete)

    if node_type == "final_output":
        final_video_path = get_existing_final_video_path(bundle, output_root=root)
        relevant_paths = [final_video_path] if final_video_path is not None else []
        return _build_material(relevant_paths, is_complete=bool(final_video_path))

    shot = bundle.find_shot(node_key)
    if shot is None:
        return _NodeMaterial(has_version=False, is_complete=False, created_at=None, relevant_paths=[])

    shot_root = root / "shots" / node_key
    keyframe_paths = _glob_existing_files(shot_root, f"{node_key}_keyframe*")

    if node_type == "prepare_shot":
        prompt_ready = bool(shot.keyframe_prompt or shot.video_prompt or shot.reference_bindings)
        relevant_paths = keyframe_paths or ([bundle_path] if prompt_ready and bundle_path.exists() else [])
        is_complete = shot.status in {"prompt_ready", "generated"} or bool(keyframe_paths)
        return _build_material(relevant_paths, is_complete=is_complete)

    if node_type == "generate_shot":
        relevant_paths = keyframe_paths[:]
        relevant_paths.extend(_collect_existing_paths([Path(asset.path) for asset in shot.output_assets if asset.path]))
        relevant_paths.extend(_glob_existing_files(root / "videos", f"{node_key}*.mp4"))
        has_video = any(path.suffix.lower() == ".mp4" for path in relevant_paths)
        is_complete = shot.status == "generated" or has_video
        return _build_material(relevant_paths, is_complete=is_complete)

    return _NodeMaterial(has_version=False, is_complete=False, created_at=None, relevant_paths=[])


def _build_material(relevant_paths: list[Path], *, is_complete: bool) -> _NodeMaterial:
    unique_paths = _dedupe_paths(relevant_paths)
    if not unique_paths:
        return _NodeMaterial(has_version=False, is_complete=False, created_at=None, relevant_paths=[])
    latest_path = max(unique_paths, key=lambda path: path.stat().st_mtime_ns)
    created_at = datetime.fromtimestamp(latest_path.stat().st_mtime_ns / 1_000_000_000, timezone.utc).isoformat()
    return _NodeMaterial(
        has_version=True,
        is_complete=is_complete,
        created_at=created_at,
        relevant_paths=unique_paths,
    )


def _has_user_input_content(bundle) -> bool:
    topic_text = str(getattr(getattr(bundle, "topic_input", None), "topic", "") or "").strip()
    storyboard_text = str(getattr(bundle, "source_storyboard", "") or "").strip()
    return bool(topic_text or storyboard_text)


def _collect_existing_paths(paths: list[Path]) -> list[Path]:
    return [path.expanduser().resolve() for path in paths if path.expanduser().exists()]


def _glob_existing_files(root: Path, pattern: str) -> list[Path]:
    if not root.exists():
        return []
    return [path.resolve() for path in sorted(root.glob(pattern)) if path.is_file()]


def _dedupe_paths(paths: list[Path]) -> list[Path]:
    unique_paths: list[Path] = []
    seen_paths: set[Path] = set()
    for path in paths:
        resolved_path = path.resolve()
        if resolved_path in seen_paths:
            continue
        seen_paths.add(resolved_path)
        unique_paths.append(resolved_path)
    return unique_paths


def _build_inferred_version_id(
    *,
    node_type: str,
    node_key: str,
    created_at: datetime,
) -> str:
    timestamp_text = created_at.astimezone(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    normalized_key = PROJECT_NODE_KEY if node_key == PROJECT_NODE_KEY else node_key
    return f"version_{node_type}_{normalized_key}_{timestamp_text}"


def _parse_iso_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value)
