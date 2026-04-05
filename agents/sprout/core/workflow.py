"""Sprout 核心端到端工作流。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .character_builder import SproutCharacterBuilder
from .exporter import SproutExporter
from .jimeng_packager import SproutJimengPackager
from .project_store import SproutProjectStore
from .schema import SproutProjectBundle, SproutTopicInput
from .script_planner import SproutScriptPlanner
from .shot_pipeline import SproutShotPipeline
from .utils import ensure_directory, write_json_file, write_text_file


@dataclass
class SproutWorkflow:
    """Sprout 主工作流。"""

    script_planner: SproutScriptPlanner | None = None
    character_builder: SproutCharacterBuilder | None = None
    shot_pipeline: SproutShotPipeline | None = None
    jimeng_packager: SproutJimengPackager | None = None
    exporter: SproutExporter | None = None
    project_store: SproutProjectStore | None = None

    def run_from_topic(
        self,
        topic_input: SproutTopicInput | str,
        *,
        output_root: str | Path,
        project_name: str | None = None,
        extra_reference_count: int = 0,
        generate_video_shot_count: int = 1,
    ) -> SproutProjectBundle:
        project_bundle = self.plan_from_topic(
            topic_input=topic_input,
            output_root=output_root,
            project_name=project_name,
        )
        return self.run_after_planning(
            project_bundle=project_bundle,
            output_root=output_root,
            extra_reference_count=extra_reference_count,
            generate_video_shot_count=generate_video_shot_count,
            storyboard_text=None,
        )

    def run_from_storyboard(
        self,
        storyboard_text: str,
        *,
        output_root: str | Path,
        topic_input: SproutTopicInput | None = None,
        project_name: str | None = None,
        extra_reference_count: int = 0,
        generate_video_shot_count: int = 1,
    ) -> SproutProjectBundle:
        project_bundle = self.plan_from_storyboard(
            storyboard_text=storyboard_text,
            output_root=output_root,
            topic_input=topic_input,
            project_name=project_name,
        )
        return self.run_after_planning(
            project_bundle=project_bundle,
            output_root=output_root,
            extra_reference_count=extra_reference_count,
            generate_video_shot_count=generate_video_shot_count,
            storyboard_text=storyboard_text,
        )

    def plan_from_topic(
        self,
        *,
        topic_input: SproutTopicInput | str,
        output_root: str | Path | None = None,
        project_name: str | None = None,
    ) -> SproutProjectBundle:
        resolved_input = (
            topic_input if isinstance(topic_input, SproutTopicInput) else SproutTopicInput(topic=topic_input)
        )
        project_bundle = self._get_script_planner().plan_from_topic(
            resolved_input,
            project_name=project_name,
        )
        if output_root is not None:
            self._save_input_files(
                project_bundle=project_bundle,
                output_root=ensure_directory(output_root),
                storyboard_text=None,
            )
            self._get_project_store().save_bundle(
                project_bundle,
                output_root=output_root,
            )
        return project_bundle

    def plan_from_storyboard(
        self,
        *,
        storyboard_text: str,
        output_root: str | Path | None = None,
        topic_input: SproutTopicInput | None = None,
        project_name: str | None = None,
    ) -> SproutProjectBundle:
        project_bundle = self._get_script_planner().plan_from_storyboard(
            storyboard_text=storyboard_text,
            topic_input=topic_input,
            project_name=project_name,
        )
        if output_root is not None:
            self._save_input_files(
                project_bundle=project_bundle,
                output_root=ensure_directory(output_root),
                storyboard_text=storyboard_text,
            )
            self._get_project_store().save_bundle(
                project_bundle,
                output_root=output_root,
            )
        return project_bundle

    def run_after_planning(
        self,
        *,
        project_bundle: SproutProjectBundle,
        output_root: str | Path,
        extra_reference_count: int,
        generate_video_shot_count: int,
        storyboard_text: str | None,
    ) -> SproutProjectBundle:
        output_root_path = ensure_directory(output_root)
        self._save_input_files(
            project_bundle=project_bundle,
            output_root=output_root_path,
            storyboard_text=storyboard_text,
        )

        self.build_characters(
            project_bundle=project_bundle,
            output_root=output_root_path,
            extra_reference_count=extra_reference_count,
        )
        self.prepare_shots(
            project_bundle=project_bundle,
            output_root=output_root_path,
        )

        if generate_video_shot_count > 0:
            self.generate_shots(
                project_bundle=project_bundle,
                output_root=output_root_path,
                shot_count=generate_video_shot_count,
            )

        self.build_workflow_cards(
            project_bundle=project_bundle,
            output_root=output_root_path,
        )
        self.export_bundle(
            project_bundle=project_bundle,
            output_root=output_root_path,
        )
        return project_bundle

    def build_characters(
        self,
        *,
        project_bundle: SproutProjectBundle,
        output_root: str | Path,
        extra_reference_count: int = 0,
        skip_existing: bool = True,
    ) -> SproutProjectBundle:
        self._get_character_builder().generate_character_assets(
            project_bundle,
            output_root=output_root,
            extra_reference_count=extra_reference_count,
            skip_existing=skip_existing,
        )
        self._get_project_store().save_bundle(project_bundle, output_root=output_root)
        return project_bundle

    def prepare_shots(
        self,
        *,
        project_bundle: SproutProjectBundle,
        output_root: str | Path | None = None,
        shot_ids: list[str] | None = None,
    ) -> SproutProjectBundle:
        normalized_ids = {shot_id.strip().lower() for shot_id in (shot_ids or []) if shot_id.strip()}
        for shot in project_bundle.shots:
            if normalized_ids and shot.shot_id.lower() not in normalized_ids:
                continue
            self._get_shot_pipeline().prepare_shot(project_bundle, shot)
        if output_root is not None:
            self._get_project_store().save_bundle(project_bundle, output_root=output_root)
        return project_bundle

    def generate_shots(
        self,
        *,
        project_bundle: SproutProjectBundle,
        output_root: str | Path,
        shot_count: int | None = None,
        shot_ids: list[str] | None = None,
        skip_existing: bool = True,
    ) -> SproutProjectBundle:
        if shot_ids:
            self._get_shot_pipeline().generate_selected_shots(
                project_bundle,
                output_root=output_root,
                shot_ids=shot_ids,
                skip_existing=skip_existing,
            )
        else:
            self._get_shot_pipeline().generate_first_n_shots(
                project_bundle,
                output_root=output_root,
                shot_count=shot_count or 1,
                skip_existing=skip_existing,
            )
        self._get_project_store().save_bundle(project_bundle, output_root=output_root)
        return project_bundle

    def build_workflow_cards(
        self,
        *,
        project_bundle: SproutProjectBundle,
        output_root: str | Path | None = None,
    ) -> SproutProjectBundle:
        self._get_packager().build_cards(project_bundle)
        if output_root is not None:
            self._get_project_store().save_bundle(project_bundle, output_root=output_root)
        return project_bundle

    def export_bundle(
        self,
        *,
        project_bundle: SproutProjectBundle,
        output_root: str | Path,
    ) -> dict[str, Path]:
        self._get_project_store().save_bundle(project_bundle, output_root=output_root)
        return self._get_exporter().export_bundle(
            project_bundle,
            output_root=output_root,
        )

    def configure_video_model_preferences(
        self,
        *,
        single_reference_model_name: str | None = None,
        multi_reference_model_name: str | None = None,
        fallback_multi_reference_model_names: list[str] | None = None,
    ) -> None:
        shot_pipeline = self._get_shot_pipeline()
        if single_reference_model_name:
            shot_pipeline.single_reference_model_name = single_reference_model_name
        if multi_reference_model_name:
            shot_pipeline.multi_reference_model_name = multi_reference_model_name
        if fallback_multi_reference_model_names is not None:
            shot_pipeline.fallback_multi_reference_model_names = tuple(
                model_name.strip()
                for model_name in fallback_multi_reference_model_names
                if model_name.strip()
            )

    def _save_input_files(
        self,
        *,
        project_bundle: SproutProjectBundle,
        output_root: str | Path,
        storyboard_text: str | None,
    ) -> None:
        input_root = ensure_directory(Path(output_root) / "input")
        write_json_file(
            input_root / f"{project_bundle.project_name}_topic_input.json",
            project_bundle.topic_input.to_dict(),
        )
        if storyboard_text:
            write_text_file(
                input_root / f"{project_bundle.project_name}_storyboard.txt",
                storyboard_text,
            )

    def _get_script_planner(self) -> SproutScriptPlanner:
        if self.script_planner is None:
            self.script_planner = SproutScriptPlanner()
        return self.script_planner

    def _get_character_builder(self) -> SproutCharacterBuilder:
        if self.character_builder is None:
            self.character_builder = SproutCharacterBuilder()
        return self.character_builder

    def _get_shot_pipeline(self) -> SproutShotPipeline:
        if self.shot_pipeline is None:
            self.shot_pipeline = SproutShotPipeline()
        return self.shot_pipeline

    def _get_packager(self) -> SproutJimengPackager:
        if self.jimeng_packager is None:
            self.jimeng_packager = SproutJimengPackager()
        return self.jimeng_packager

    def _get_exporter(self) -> SproutExporter:
        if self.exporter is None:
            self.exporter = SproutExporter(jimeng_packager=self._get_packager())
        return self.exporter

    def _get_project_store(self) -> SproutProjectStore:
        if self.project_store is None:
            self.project_store = SproutProjectStore()
        return self.project_store
