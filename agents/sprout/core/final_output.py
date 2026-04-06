"""Sprout 最终成片相关能力。"""

from __future__ import annotations

from pathlib import Path

from .schema import SproutAsset, SproutProjectBundle
from .utils import ensure_directory

FINAL_OUTPUT_NODE_TYPE = "final_output"
FINAL_VIDEO_ASSET_TYPE = "final_video"


def get_final_video_asset_id(project_name: str) -> str:
    """返回最终成片资产 ID。"""

    return f"{project_name}_final_video"


def get_final_video_output_path(output_root: str | Path, project_name: str) -> Path:
    """返回最终成片默认输出路径。"""

    videos_root = ensure_directory(Path(output_root).expanduser() / "videos")
    return videos_root / f"{project_name}_final_cut.mp4"


def find_final_video_asset(project_bundle: SproutProjectBundle) -> SproutAsset | None:
    """在 bundle 中查找最终成片资产。"""

    for asset in project_bundle.assets:
        if asset.asset_type == FINAL_VIDEO_ASSET_TYPE:
            return asset
        if asset.asset_id == get_final_video_asset_id(project_bundle.project_name):
            return asset
    return None


def get_existing_final_video_path(
    project_bundle: SproutProjectBundle,
    *,
    output_root: str | Path | None = None,
) -> Path | None:
    """返回已存在的最终成片路径。"""

    asset = find_final_video_asset(project_bundle)
    if asset and asset.path:
        asset_path = Path(asset.path).expanduser()
        if asset_path.exists():
            return asset_path.resolve()

    if output_root is None:
        return None

    output_path = get_final_video_output_path(output_root, project_bundle.project_name)
    if output_path.exists():
        return output_path.resolve()
    return None


def collect_final_video_segment_paths(project_bundle: SproutProjectBundle) -> list[Path]:
    """按镜头顺序收集用于拼接的源视频。"""

    segment_paths: list[Path] = []
    for shot in project_bundle.shots:
        shot_video_path = None
        for asset in shot.output_assets:
            if asset.asset_type != "shot_video" or not asset.path:
                continue
            candidate_path = Path(asset.path).expanduser()
            if candidate_path.exists():
                shot_video_path = candidate_path.resolve()
                break
        if shot_video_path is None:
            raise ValueError(f"镜头 {shot.shot_id} 还没有可用视频，无法合成最终成片。")
        segment_paths.append(shot_video_path)
    return segment_paths


def upsert_final_video_asset(
    project_bundle: SproutProjectBundle,
    *,
    final_video_path: str | Path,
    segment_count: int,
    resolution_report: dict[str, object] | None = None,
) -> SproutAsset:
    """在 bundle 中写入或更新最终成片资产。"""

    resolved_path = str(Path(final_video_path).expanduser().resolve())
    asset_id = get_final_video_asset_id(project_bundle.project_name)
    existing_asset = find_final_video_asset(project_bundle)
    if existing_asset is not None:
        existing_asset.asset_id = asset_id
        existing_asset.asset_type = FINAL_VIDEO_ASSET_TYPE
        existing_asset.source = FINAL_OUTPUT_NODE_TYPE
        existing_asset.path = resolved_path
        existing_asset.role = "final_video"
        existing_asset.owner_id = "project"
        existing_asset.metadata = {
            **dict(existing_asset.metadata),
            "segment_count": segment_count,
            "resolution_report": dict(resolution_report or {}),
        }
        return existing_asset

    final_asset = SproutAsset(
        asset_id=asset_id,
        asset_type=FINAL_VIDEO_ASSET_TYPE,
        source=FINAL_OUTPUT_NODE_TYPE,
        path=resolved_path,
        role="final_video",
        owner_id="project",
        metadata={
            "segment_count": segment_count,
            "resolution_report": dict(resolution_report or {}),
        },
    )
    project_bundle.assets.append(final_asset)
    return final_asset
