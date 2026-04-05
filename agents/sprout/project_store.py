"""Sprout 项目状态读写。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .schema import SproutProjectBundle
from .utils import ensure_directory, read_json_file, write_json_file


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
        payload = read_json_file(bundle_path)
        if not isinstance(payload, dict):
            raise ValueError("bundle 文件内容必须为 JSON 对象。")
        return SproutProjectBundle.from_dict(payload)
