"""Sprout 核心镜头生成链路。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from module.api.seed import SeedImageClient, SeedVideoAPIError, SeedVideoClient

from .schema import (
    SproutAsset,
    SproutCharacter,
    SproutProjectBundle,
    SproutReferenceBinding,
    SproutShot,
)
from .utils import ensure_directory


@dataclass
class SproutShotPipeline:
    """负责关键帧、绑定 prompt 和视频生成。"""

    image_client: SeedImageClient | None = None
    video_client: SeedVideoClient | None = None
    multi_reference_model_name: str = "doubao-seedance-2-0-fast"
    fallback_multi_reference_model_names: tuple[str, ...] = ("doubao-seedance-2-0",)
    single_reference_model_name: str | None = None

    def prepare_shot(
        self,
        project_bundle: SproutProjectBundle,
        shot: SproutShot,
    ) -> SproutShot:
        """仅生成 prompt 和角色绑定，不调用远端接口。"""

        character_assets = self._resolve_character_assets(project_bundle, shot)
        shot.keyframe_prompt = self.build_keyframe_prompt(shot=shot, characters=character_assets)
        provisional_bindings = self._build_character_bindings(character_assets)
        shot.video_prompt = self.build_video_prompt(
            shot=shot,
            bindings=provisional_bindings,
            include_first_frame=False,
        )
        shot.reference_bindings = provisional_bindings
        shot.prompt_options = self.build_prompt_options(shot)
        shot.status = "prompt_ready"
        return shot

    def generate_single_shot(
        self,
        project_bundle: SproutProjectBundle,
        shot: SproutShot,
        *,
        output_root: str | Path,
        skip_existing: bool = True,
    ) -> SproutShot:
        """生成单个镜头的关键帧与视频。"""

        if skip_existing and self._has_generated_output(shot):
            shot.status = "generated"
            return shot

        prepared_shot = self.prepare_shot(project_bundle, shot)
        character_assets = self._resolve_character_assets(project_bundle, prepared_shot)
        reference_image_paths = [asset.path for _, asset in character_assets if asset.path]
        use_multireference_mode = len(reference_image_paths) > 0

        shot_root = ensure_directory(Path(output_root) / "shots" / prepared_shot.shot_id)
        videos_root = ensure_directory(Path(output_root) / "videos")
        keyframe_path = self._get_image_client().generate_and_save_single(
            prompt=prepared_shot.keyframe_prompt or "",
            output_dir=shot_root,
            reference_images=reference_image_paths or None,
            file_name_prefix=f"{prepared_shot.shot_id}_keyframe",
        )
        keyframe_asset = SproutAsset(
            asset_id=f"{prepared_shot.shot_id}_keyframe",
            asset_type="shot_keyframe",
            source="seed_image",
            path=str(keyframe_path),
            role="first_frame",
            prompt=prepared_shot.keyframe_prompt,
            owner_id=prepared_shot.shot_id,
            metadata={"shot_index": prepared_shot.shot_index},
        )

        final_bindings = self._build_video_bindings(
            keyframe_asset=keyframe_asset,
            character_assets=character_assets,
            include_keyframe_in_binding=use_multireference_mode,
        )
        prepared_shot.reference_bindings = final_bindings
        prepared_shot.video_prompt = self.build_video_prompt(
            shot=prepared_shot,
            bindings=final_bindings,
            include_first_frame=use_multireference_mode,
        )

        if use_multireference_mode:
            saved_video_paths = self._generate_multireference_video(
                shot=prepared_shot,
                keyframe_path=keyframe_path,
                reference_image_paths=reference_image_paths,
                output_dir=videos_root,
            )
        else:
            saved_video_paths = self._get_video_client().create_image_to_video_and_save(
                prompt=prepared_shot.video_prompt,
                image_input=str(keyframe_path),
                output_dir=videos_root,
                reference_images=None,
                image_role="first_frame",
                prompt_options=prepared_shot.prompt_options,
                model_name=self._resolve_video_model_name(use_multireference_mode=False),
                file_name_prefix=prepared_shot.shot_id,
            )

        prepared_shot.output_assets = [keyframe_asset]
        for index, saved_video_path in enumerate(saved_video_paths, start=1):
            prepared_shot.output_assets.append(
                SproutAsset(
                    asset_id=f"{prepared_shot.shot_id}_video_{index:02d}",
                    asset_type="shot_video",
                    source="seed_video",
                    path=str(saved_video_path),
                    role="video",
                    prompt=prepared_shot.video_prompt,
                    owner_id=prepared_shot.shot_id,
                    metadata={"shot_index": prepared_shot.shot_index},
                )
            )
        prepared_shot.status = "generated"

        for asset in prepared_shot.output_assets:
            project_bundle.register_asset(asset)
        project_bundle.ensure_manifest(output_root=str(Path(output_root)))
        return prepared_shot

    def generate_first_n_shots(
        self,
        project_bundle: SproutProjectBundle,
        *,
        output_root: str | Path,
        shot_count: int = 1,
        skip_existing: bool = True,
    ) -> SproutProjectBundle:
        """按顺序生成前 N 个镜头。"""

        for shot in project_bundle.shots[: max(shot_count, 0)]:
            self.generate_single_shot(
                project_bundle=project_bundle,
                shot=shot,
                output_root=output_root,
                skip_existing=skip_existing,
            )
        project_bundle.ensure_manifest(output_root=str(Path(output_root)))
        return project_bundle

    def generate_selected_shots(
        self,
        project_bundle: SproutProjectBundle,
        *,
        output_root: str | Path,
        shot_ids: list[str] | None = None,
        skip_existing: bool = True,
    ) -> SproutProjectBundle:
        """按镜头 ID 生成指定镜头。"""

        if not shot_ids:
            return project_bundle

        normalized_ids = {shot_id.strip().lower() for shot_id in shot_ids if shot_id.strip()}
        for shot in project_bundle.shots:
            if shot.shot_id.lower() not in normalized_ids:
                continue
            self.generate_single_shot(
                project_bundle=project_bundle,
                shot=shot,
                output_root=output_root,
                skip_existing=skip_existing,
            )
        project_bundle.ensure_manifest(output_root=str(Path(output_root)))
        return project_bundle

    def build_prompt_options(self, shot: SproutShot) -> dict[str, int]:
        """构建视频生成的附加参数。"""

        return {"duration": min(max(shot.duration_seconds, 1), 15)}

    def build_keyframe_prompt(
        self,
        *,
        shot: SproutShot,
        characters: list[tuple[SproutCharacter, SproutAsset]],
    ) -> str:
        character_text = "、".join(character.name for character, _ in characters) or "无明确角色"
        prompt_segments = [
            f"镜头标题：{shot.title}",
            f"出镜角色：{character_text}",
            f"画面描述：{shot.visual_description or '请根据镜头标题补足画面'}",
            f"机位语言：{shot.camera_language or '竖屏短剧镜头'}",
            f"情绪：{shot.emotion or '戏剧张力明确'}",
        ]
        if shot.notes:
            prompt_segments.append(f"制作备注：{shot.notes}")
        prompt_segments.append("请生成适合图生视频首帧的关键画面，人物造型稳定，方便后续视频延展。")
        return "；".join(prompt_segments)

    def build_video_prompt(
        self,
        *,
        shot: SproutShot,
        bindings: list[SproutReferenceBinding],
        include_first_frame: bool,
    ) -> str:
        binding_lines: list[str] = []
        for binding in bindings:
            if include_first_frame or binding.usage != "first_frame":
                binding_lines.append(binding.prompt_fragment or "")

        prompt_segments = []
        if binding_lines:
            prompt_segments.append("参考图绑定：" + "；".join(binding_lines))
        prompt_segments.append(f"镜头标题：{shot.title}")
        prompt_segments.append(f"镜头画面：{shot.visual_description or ''}")
        if shot.camera_language:
            prompt_segments.append(f"镜头语言：{shot.camera_language}")
        if shot.emotion:
            prompt_segments.append(f"情绪目标：{shot.emotion}")
        if shot.dialogue:
            prompt_segments.append(f"台词：{shot.dialogue}")
            prompt_segments.append("请根据台词生成匹配配音，尽量保证口型与情绪一致")
        if shot.sound_effects:
            prompt_segments.append(f"音效：{shot.sound_effects}")
            prompt_segments.append("请同步生成贴合画面的环境音与动作音效")
        if shot.notes:
            prompt_segments.append(f"补充说明：{shot.notes}")
        prompt_segments.append("请保持人物一致性与叙事连续性，适合竖屏短剧传播，并输出有声视频。")
        return "；".join(segment for segment in prompt_segments if segment)

    def _resolve_character_assets(
        self,
        project_bundle: SproutProjectBundle,
        shot: SproutShot,
    ) -> list[tuple[SproutCharacter, SproutAsset]]:
        resolved_assets: list[tuple[SproutCharacter, SproutAsset]] = []
        for character_name in shot.characters:
            character = project_bundle.find_character(character_name)
            if character is None:
                raise ValueError(f"镜头 {shot.shot_id} 中的角色未定义：{character_name}")
            if not character.reference_assets:
                raise ValueError(f"角色 {character.name} 尚未生成参考图，无法生成镜头。")
            resolved_assets.append((character, character.reference_assets[0]))
        return resolved_assets

    def _build_character_bindings(
        self,
        character_assets: list[tuple[SproutCharacter, SproutAsset]],
    ) -> list[SproutReferenceBinding]:
        bindings: list[SproutReferenceBinding] = []
        for index, (character, asset) in enumerate(character_assets, start=1):
            bindings.append(
                SproutReferenceBinding(
                    binding_index=index,
                    placeholder=f"[图{index}]",
                    asset_id=asset.asset_id,
                    asset_path=asset.path,
                    character_id=character.character_id,
                    character_name=character.name,
                    usage="reference_image",
                    prompt_fragment=f"[图{index}] 是 {character.name} 的角色参考图，请保持长相、服装和气质一致",
                )
            )
        return bindings

    def _build_video_bindings(
        self,
        *,
        keyframe_asset: SproutAsset,
        character_assets: list[tuple[SproutCharacter, SproutAsset]],
        include_keyframe_in_binding: bool,
    ) -> list[SproutReferenceBinding]:
        bindings: list[SproutReferenceBinding] = []
        next_index = 1
        if include_keyframe_in_binding:
            bindings.append(
                SproutReferenceBinding(
                    binding_index=next_index,
                    placeholder=f"[图{next_index}]",
                    asset_id=keyframe_asset.asset_id,
                    asset_path=keyframe_asset.path,
                    usage="reference_image",
                    prompt_fragment=f"[图{next_index}] 是本镜头构图与动作参考图，请保持整体构图和动作起势一致",
                )
            )
            next_index += 1
        else:
            bindings.append(
                SproutReferenceBinding(
                    binding_index=next_index,
                    placeholder=f"[图{next_index}]",
                    asset_id=keyframe_asset.asset_id,
                    asset_path=keyframe_asset.path,
                    usage="first_frame",
                    prompt_fragment=f"[图{next_index}] 是本镜头首帧关键画面，请以它作为构图与动作起点",
                )
            )
            next_index += 1

        for index, (character, asset) in enumerate(character_assets, start=next_index):
            bindings.append(
                SproutReferenceBinding(
                    binding_index=index,
                    placeholder=f"[图{index}]",
                    asset_id=asset.asset_id,
                    asset_path=asset.path,
                    character_id=character.character_id,
                    character_name=character.name,
                    usage="reference_image",
                    prompt_fragment=f"[图{index}] 是 {character.name} 的角色参考图，请保持人物一致",
                )
            )
        return bindings

    def _get_image_client(self) -> SeedImageClient:
        if self.image_client is None:
            self.image_client = SeedImageClient()
        return self.image_client

    def _get_video_client(self) -> SeedVideoClient:
        if self.video_client is None:
            self.video_client = SeedVideoClient()
        return self.video_client

    def _has_generated_output(self, shot: SproutShot) -> bool:
        if not shot.output_assets:
            return False
        return all(asset.path and Path(asset.path).exists() for asset in shot.output_assets)

    def _resolve_video_model_name(self, *, use_multireference_mode: bool) -> str | None:
        video_client = self._get_video_client()
        if use_multireference_mode:
            return self.multi_reference_model_name or video_client.model_name
        return self.single_reference_model_name or video_client.model_name

    def _resolve_multireference_model_candidates(self) -> list[str]:
        candidate_model_names: list[str] = []
        for model_name in (self.multi_reference_model_name, *self.fallback_multi_reference_model_names):
            normalized_name = str(model_name).strip()
            if not normalized_name or normalized_name in candidate_model_names:
                continue
            candidate_model_names.append(normalized_name)
        return candidate_model_names

    @staticmethod
    def _is_retryable_multireference_model_error(exc: SeedVideoAPIError) -> bool:
        message = str(exc)
        return (
            "InvalidEndpointOrModel.NotFound" in message
            or "does not exist or you do not have access" in message
            or "does not support model" in message
        )

    def _generate_multireference_video(
        self,
        *,
        shot: SproutShot,
        keyframe_path: Path,
        reference_image_paths: list[str],
        output_dir: str | Path,
    ) -> list[Path]:
        video_client = self._get_video_client()
        content = self._build_multireference_content(
            prompt=shot.video_prompt or "",
            keyframe_path=keyframe_path,
            reference_image_paths=reference_image_paths,
        )
        final_response = None
        last_error: Exception | None = None
        for candidate_model_name in self._resolve_multireference_model_candidates():
            try:
                final_response = video_client.create_and_wait(
                    content=content,
                    model_name=candidate_model_name,
                    poll_interval_seconds=video_client.poll_interval_seconds,
                    timeout_seconds=video_client.wait_timeout_seconds,
                    generate_audio=True,
                )
                break
            except SeedVideoAPIError as exc:
                last_error = exc
                if not self._is_retryable_multireference_model_error(exc):
                    raise

        if final_response is None:
            if isinstance(last_error, SeedVideoAPIError) and self._is_retryable_multireference_model_error(last_error):
                shot.notes = self._append_runtime_note(
                    shot.notes,
                    "当前账号未开通 Seedance 2.0 多参考图模型，已回退为“多图生关键帧 + 单图图生视频”模式。",
                )
                return self._generate_single_reference_fallback_video(
                    shot=shot,
                    keyframe_path=keyframe_path,
                    output_dir=output_dir,
                )
            if last_error is not None:
                raise last_error
            raise RuntimeError("多参考图视频生成未获得有效响应。")

        return video_client.save_videos_from_response(
            response=final_response,
            output_dir=output_dir,
            file_name_prefix=shot.shot_id,
        )

    def _build_multireference_content(
        self,
        *,
        prompt: str,
        keyframe_path: Path,
        reference_image_paths: list[str],
    ) -> list[dict[str, Any]]:
        content: list[dict[str, Any]] = [
            {"type": "text", "text": prompt},
            {"type": "image", "image_path": str(keyframe_path), "role": "reference_image"},
        ]
        for reference_image_path in reference_image_paths:
            content.append(
                {
                    "type": "image",
                    "image_path": reference_image_path,
                    "role": "reference_image",
                }
            )
        return content

    def _generate_single_reference_fallback_video(
        self,
        *,
        shot: SproutShot,
        keyframe_path: Path,
        output_dir: str | Path,
    ) -> list[Path]:
        fallback_prompt = self.build_video_prompt(
            shot=shot,
            bindings=[],
            include_first_frame=False,
        )
        return self._get_video_client().create_image_to_video_and_save(
            prompt=fallback_prompt,
            image_input=str(keyframe_path),
            output_dir=output_dir,
            reference_images=None,
            image_role="first_frame",
            prompt_options=shot.prompt_options,
            model_name=self._resolve_video_model_name(use_multireference_mode=False),
            file_name_prefix=shot.shot_id,
        )

    @staticmethod
    def _append_runtime_note(original_notes: str | None, extra_note: str) -> str:
        normalized_original = (original_notes or "").strip()
        if not normalized_original:
            return extra_note
        if extra_note in normalized_original:
            return normalized_original
        return f"{normalized_original}\n{extra_note}"
