"""本机目录选择器。"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class SproutDirectoryPicker:
    """通过本机系统对话框选择项目目录。"""

    def pick_directory(self) -> dict[str, object]:
        selected_path = self._pick_directory_path()
        if selected_path is None:
            return {
                "cancelled": True,
                "project_root": None,
                "is_empty": None,
            }

        resolved_root = Path(selected_path).expanduser().resolve()
        if not resolved_root.exists():
            raise FileNotFoundError(f"所选目录不存在：{resolved_root}")

        return {
            "cancelled": False,
            "project_root": str(resolved_root),
            "is_empty": self._is_directory_empty(resolved_root),
        }

    def _pick_directory_path(self) -> str | None:
        if sys.platform != "darwin":
            raise RuntimeError("当前系统暂未支持原生目录选择器。")

        command = [
            "osascript",
            "-e",
            'tell application "Finder" to activate',
            "-e",
            "delay 0.1",
            "-e",
            'set selected_folder to choose folder with prompt "请选择 Sprout 项目目录"',
            "-e",
            "POSIX path of selected_folder",
        ]
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            selected_path = result.stdout.strip()
            return selected_path or None

        error_text = (result.stderr or result.stdout or "").strip()
        normalized_error = error_text.lower()
        if "user canceled" in normalized_error or "(-128)" in normalized_error:
            return None
        raise RuntimeError(f"目录选择失败：{error_text or '未知错误'}")

    @staticmethod
    def _is_directory_empty(root: Path) -> bool:
        try:
            next(root.iterdir())
        except StopIteration:
            return True
        return False
