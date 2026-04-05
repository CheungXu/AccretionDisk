"""Sprout 项目目录导入适配。"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from ..core.models import SproutProjectBundle
from ..core.shared import ensure_directory, read_json_file, slugify_name
from ..core.storage import SproutProjectStore
from .types import SproutImportedProjectRecord, build_runtime_id


@dataclass
class SproutProjectAdapter:
    """负责识别并导入 sprout 项目目录。"""

    managed_projects_root: str | Path | None = None
    project_store: SproutProjectStore | None = None

    def import_project(
        self,
        project_root: str | Path,
        *,
        import_mode: str = "reference",
    ) -> SproutImportedProjectRecord:
        """导入项目目录并返回注册信息。"""

        resolved_root = Path(project_root).expanduser().resolve()
        if not resolved_root.exists():
            raise FileNotFoundError(f"项目目录不存在：{resolved_root}")

        normalized_mode = import_mode.strip().lower() or "reference"
        if normalized_mode not in {"reference", "copy"}:
            raise ValueError("import_mode 仅支持 reference 或 copy。")

        canonical_root = (
            self._copy_into_managed_root(resolved_root)
            if normalized_mode == "copy"
            else resolved_root
        )
        bundle_path = self._find_single_file(canonical_root / "script", "*_bundle.json")
        manifest_path = self._find_optional_file(canonical_root / "manifest", "*_manifest.json")
        bundle = self._get_project_store().load_bundle(bundle_path)

        project_id = f"sprout_{slugify_name(bundle.project_name, default_prefix='project')}"
        display_name = bundle.episode.title or bundle.project_name
        cover_asset_path = self._pick_cover_asset_path(bundle)
        health_status = "ready" if manifest_path else "bundle_only"
        notes: list[str] = []
        if manifest_path is None:
            notes.append("缺少 manifest 文件，已按 bundle 导入。")

        return SproutImportedProjectRecord(
            project_id=project_id,
            project_type="sprout",
            display_name=display_name,
            project_name=bundle.project_name,
            project_root=str(resolved_root),
            canonical_root=str(canonical_root),
            bundle_path=str(bundle_path),
            manifest_path=str(manifest_path) if manifest_path else None,
            cover_asset_path=cover_asset_path,
            import_mode=normalized_mode,
            health_status=health_status,
            notes=notes,
        )

    def build_project_summary(
        self,
        record: SproutImportedProjectRecord,
    ) -> dict[str, object]:
        """生成项目摘要。"""

        bundle = self._get_project_store().load_bundle(record.bundle_path)
        manifest_payload = (
            read_json_file(record.manifest_path)
            if record.manifest_path and Path(record.manifest_path).exists()
            else None
        )
        if not isinstance(manifest_payload, dict):
            manifest_payload = bundle.ensure_manifest(output_root=str(Path(record.canonical_root)))
            manifest_payload = manifest_payload.to_dict()

        return {
            "project_id": record.project_id,
            "project_type": record.project_type,
            "display_name": record.display_name,
            "project_name": record.project_name,
            "project_root": record.project_root,
            "canonical_root": record.canonical_root,
            "bundle_path": record.bundle_path,
            "manifest_path": record.manifest_path,
            "cover_asset_path": record.cover_asset_path,
            "health_status": record.health_status,
            "import_mode": record.import_mode,
            "imported_at": record.imported_at,
            "last_active_at": record.last_active_at,
            "notes": list(record.notes),
            "manifest": manifest_payload,
            "episode": bundle.episode.to_dict(),
            "topic_input": bundle.topic_input.to_dict(),
            "character_count": len(bundle.characters),
            "shot_count": len(bundle.shots),
        }

    def load_bundle(self, bundle_path: str | Path) -> SproutProjectBundle:
        """读取项目 bundle。"""

        return self._get_project_store().load_bundle(bundle_path)

    def _copy_into_managed_root(self, source_root: Path) -> Path:
        managed_root = ensure_directory(self._resolve_managed_projects_root())
        target_name = slugify_name(source_root.name, default_prefix="project")
        target_root = managed_root / target_name
        if target_root.exists():
            target_root = managed_root / f"{target_name}_{build_runtime_id('copy')}"
        shutil.copytree(source_root, target_root)
        return target_root

    def _resolve_managed_projects_root(self) -> Path:
        if self.managed_projects_root is not None:
            return Path(self.managed_projects_root).expanduser()
        repo_root = Path(__file__).resolve().parents[3]
        return repo_root / "data" / "sprout" / "projects"

    @staticmethod
    def _find_single_file(root: Path, pattern: str) -> Path:
        if not root.exists():
            raise FileNotFoundError(f"缺少目录：{root}")
        matches = sorted(root.glob(pattern))
        if not matches:
            raise FileNotFoundError(f"在 {root} 中未找到 {pattern}")
        return matches[0]

    @staticmethod
    def _find_optional_file(root: Path, pattern: str) -> Path | None:
        if not root.exists():
            return None
        matches = sorted(root.glob(pattern))
        return matches[0] if matches else None

    @staticmethod
    def _pick_cover_asset_path(bundle: SproutProjectBundle) -> str | None:
        for shot in bundle.shots:
            for asset in shot.output_assets:
                if asset.asset_type == "shot_video" and asset.path:
                    return asset.path
            for asset in shot.output_assets:
                if asset.path:
                    return asset.path
        for character in bundle.characters:
            for asset in character.reference_assets:
                if asset.path:
                    return asset.path
        return None

    def _get_project_store(self) -> SproutProjectStore:
        if self.project_store is None:
            self.project_store = SproutProjectStore()
        return self.project_store
