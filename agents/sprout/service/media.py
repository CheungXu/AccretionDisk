"""Sprout 媒体访问服务。"""

from __future__ import annotations

import mimetypes
from dataclasses import dataclass
from pathlib import Path

from .registry import SproutProjectRegistry


@dataclass
class SproutMediaService:
    """负责校验并读取项目内媒体文件。"""

    registry: SproutProjectRegistry | None = None

    def read_project_media(self, project_id: str, asset_path: str) -> tuple[str, bytes]:
        record = self._get_registry().get_project(project_id)
        resolved_path = Path(asset_path).expanduser().resolve()
        project_root = Path(record.canonical_root).expanduser().resolve()

        if not resolved_path.exists():
            raise FileNotFoundError(f"媒体文件不存在：{resolved_path}")
        if not self._is_relative_to(resolved_path, project_root):
            raise PermissionError("仅允许访问项目目录下的媒体文件。")

        mime_type, _ = mimetypes.guess_type(str(resolved_path))
        return mime_type or "application/octet-stream", resolved_path.read_bytes()

    @staticmethod
    def _is_relative_to(path: Path, root: Path) -> bool:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            return False

    def _get_registry(self) -> SproutProjectRegistry:
        if self.registry is None:
            self.registry = SproutProjectRegistry()
        return self.registry
