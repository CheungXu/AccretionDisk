"""Sprout 项目导出器。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .jimeng_packager import SproutJimengPackager
from .schema import SproutProjectBundle
from .utils import ensure_directory, write_json_file, write_text_file


@dataclass
class SproutExporter:
    """负责导出项目清单与执行卡。"""

    jimeng_packager: SproutJimengPackager | None = None

    def export_bundle(
        self,
        project_bundle: SproutProjectBundle,
        *,
        output_root: str | Path,
    ) -> dict[str, Path]:
        output_root_path = ensure_directory(output_root)
        script_root = ensure_directory(output_root_path / "script")
        manifest_root = ensure_directory(output_root_path / "manifest")
        workflow_root = ensure_directory(output_root_path / "workflow_cards")

        if not project_bundle.workflow_cards:
            self._get_packager().build_cards(project_bundle)

        manifest = project_bundle.ensure_manifest(output_root=str(output_root_path))
        manifest.status = "ready" if project_bundle.workflow_cards else "draft"

        exported_paths = {
            "project_bundle_json": write_json_file(
                script_root / f"{project_bundle.project_name}_bundle.json",
                project_bundle.to_dict(),
            ),
            "project_manifest_json": write_json_file(
                manifest_root / f"{project_bundle.project_name}_manifest.json",
                manifest.to_dict(),
            ),
            "project_summary_md": write_text_file(
                manifest_root / f"{project_bundle.project_name}_summary.md",
                self.render_project_summary(project_bundle),
            ),
        }

        for workflow_card in project_bundle.workflow_cards:
            exported_paths[f"workflow_card_{workflow_card.shot_id}"] = write_text_file(
                workflow_root / f"{workflow_card.shot_id}.md",
                self._get_packager().render_card_markdown(workflow_card),
            )
        return exported_paths

    def render_project_summary(self, project_bundle: SproutProjectBundle) -> str:
        character_lines = "\n".join(
            f"- `{character.character_id}`：{character.name}，{character.summary or character.role or '待补充'}"
            for character in project_bundle.characters
        ) or "- 无"
        shot_lines = "\n".join(
            (
                f"- `{shot.shot_id}`：{shot.title}，"
                f"{shot.duration_seconds} 秒，"
                f"角色：{'、'.join(shot.characters) or '无'}，"
                f"状态：{shot.status}"
            )
            for shot in project_bundle.shots
        ) or "- 无"
        asset_lines = "\n".join(
            f"- `{asset.asset_id}`：{asset.asset_type} -> {asset.path or asset.url or '无路径'}"
            for asset in project_bundle.assets
        ) or "- 无"

        return (
            f"# {project_bundle.episode.title}\n\n"
            f"- 项目名：`{project_bundle.project_name}`\n"
            f"- 题材：{project_bundle.topic_input.topic}\n"
            f"- 总时长：`{project_bundle.episode.total_duration_seconds}` 秒\n"
            f"- 镜头数：`{len(project_bundle.shots)}`\n"
            f"- 视觉风格：{project_bundle.episode.visual_style or '未指定'}\n"
            f"- 核心卖点：{project_bundle.episode.core_hook or '未指定'}\n\n"
            "## 角色\n"
            f"{character_lines}\n\n"
            "## 镜头\n"
            f"{shot_lines}\n\n"
            "## 资产\n"
            f"{asset_lines}\n"
        )

    def _get_packager(self) -> SproutJimengPackager:
        if self.jimeng_packager is None:
            self.jimeng_packager = SproutJimengPackager()
        return self.jimeng_packager
