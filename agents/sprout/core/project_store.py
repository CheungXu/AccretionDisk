"""Sprout 核心项目状态读写。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .schema import SproutProjectBundle
from .utils import ensure_directory, read_json_file, write_json_file


PATH_ANCHORS = (
    "characters",
    "shots",
    "videos",
    "workflow_cards",
    "manifest",
    "script",
    "input",
    "runtime",
)


@dataclass
class SproutProjectStore:
    """负责保存和读取项目包。"""

    def get_default_bundle_path(
        self,
        *,
        output_root: str | Path,
        project_name: str,
    ) -> Path:
        script_root = ensure_directory(Path(output_root).expanduser() / "script")
        return script_root / f"{project_name}_bundle.json"

    def save_bundle(
        self,
        project_bundle: SproutProjectBundle,
        *,
        output_root: str | Path | None = None,
        bundle_path: str | Path | None = None,
    ) -> Path:
        if bundle_path is None:
            if output_root is None:
                raise ValueError("output_root 和 bundle_path 不能同时为空。")
            bundle_path = self.get_default_bundle_path(
                output_root=output_root,
                project_name=project_bundle.project_name,
            )
        if output_root is not None:
            project_bundle.ensure_manifest(output_root=str(Path(output_root).expanduser()))
        saved_path = write_json_file(bundle_path, project_bundle.to_dict())
        if output_root is None:
            project_bundle.ensure_manifest(output_root=str(Path(saved_path).expanduser().parent.parent))
        return saved_path

    def load_bundle(self, bundle_path: str | Path) -> SproutProjectBundle:
        resolved_bundle_path = Path(bundle_path).expanduser().resolve()
        payload = read_json_file(resolved_bundle_path)
        if not isinstance(payload, dict):
            raise ValueError("bundle 文件内容必须为 JSON 对象。")
        bundle = SproutProjectBundle.from_dict(payload)
        project_root = infer_project_root_from_bundle_path(resolved_bundle_path)
        if project_root is not None:
            normalize_bundle_media_paths(bundle, project_root)
        return bundle


def infer_project_root_from_bundle_path(bundle_path: str | Path) -> Path | None:
    """根据 bundle 文件位置推断项目根目录。"""

    resolved_path = Path(bundle_path).expanduser().resolve()
    if resolved_path.parent.name == "script":
        return resolved_path.parent.parent
    if resolved_path.parent.name == "version_snapshots" and resolved_path.parent.parent.name == "runtime":
        return resolved_path.parent.parent.parent
    return None


def normalize_bundle_media_paths(project_bundle: SproutProjectBundle, project_root: str | Path) -> None:
    """将 bundle 中的旧绝对路径归一化到当前项目根目录。"""

    resolved_project_root = Path(project_root).expanduser().resolve()

    for character in project_bundle.characters:
        for asset in character.reference_assets:
            asset.path = normalize_project_path(resolved_project_root, asset.path)

    for shot in project_bundle.shots:
        for binding in shot.reference_bindings:
            binding.asset_path = normalize_project_path(resolved_project_root, binding.asset_path)
        for asset in shot.output_assets:
            asset.path = normalize_project_path(resolved_project_root, asset.path)

    for asset in project_bundle.assets:
        asset.path = normalize_project_path(resolved_project_root, asset.path)

    for card in project_bundle.workflow_cards:
        card.upload_sequence = [
            normalize_upload_sequence_item(item, resolved_project_root)
            for item in card.upload_sequence
        ]

    if project_bundle.manifest is not None:
        project_bundle.manifest.output_root = normalize_project_root_path(
            resolved_project_root,
            project_bundle.manifest.output_root,
        )


def normalize_upload_sequence_item(value: str, project_root: Path) -> str:
    """修正工作流卡中的上传路径文本。"""

    text = str(value or "").strip()
    if "->" not in text:
        return text

    left, right = text.split("->", 1)
    normalized_path = normalize_project_path(project_root, right.strip())
    if not normalized_path:
        return text
    return f"{left.strip()} -> {normalized_path}"


def normalize_project_root_path(project_root: Path, value: str | None) -> str | None:
    """修正 manifest.output_root 一类项目根路径。"""

    normalized_value = str(value or "").strip()
    if not normalized_value:
        return None
    candidate_path = Path(normalized_value).expanduser()
    if candidate_path.exists():
        return str(candidate_path.resolve())
    return str(project_root)


def normalize_project_path(project_root: Path, value: str | None) -> str | None:
    """将旧机器上的绝对路径归一化到当前项目根目录。"""

    normalized_value = str(value or "").strip()
    if not normalized_value:
        return None

    candidate_path = Path(normalized_value).expanduser()
    if candidate_path.exists():
        return str(candidate_path.resolve())

    if not candidate_path.is_absolute():
        relative_candidate = (project_root / candidate_path).resolve()
        if relative_candidate.exists():
            return str(relative_candidate)

    path_parts = candidate_path.parts
    for anchor in PATH_ANCHORS:
        if anchor not in path_parts:
            continue
        anchor_index = path_parts.index(anchor)
        relative_suffix = Path(*path_parts[anchor_index:])
        anchored_candidate = (project_root / relative_suffix).resolve()
        if anchored_candidate.exists():
            return str(anchored_candidate)

    return normalized_value
