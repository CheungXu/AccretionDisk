"""Sprout 角色资产生成。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from module.api.seed import SeedImageClient

from .schema import SproutAsset, SproutCharacter, SproutProjectBundle
from .utils import ensure_directory


@dataclass
class SproutCharacterBuilder:
    """负责生成角色定妆图与补充参考图。"""

    image_client: SeedImageClient | None = None

    def build_character_prompt(
        self,
        character: SproutCharacter,
        *,
        visual_style: str | None = None,
    ) -> str:
        prompt_segments = [
            f"角色名：{character.name}",
            f"角色定位：{character.role or '核心人物'}",
            f"人物简介：{character.summary or '请根据上下文补足角色气质'}",
            f"外形描述：{character.appearance or character.appearance_prompt or '风格统一的人物定妆图'}",
        ]
        if character.personality:
            prompt_segments.append(f"性格关键词：{character.personality}")
        if visual_style:
            prompt_segments.append(f"视觉风格：{visual_style}")
        if character.notes:
            prompt_segments.append(f"补充说明：{character.notes}")
        prompt_segments.append("请输出适合后续视频绑定的单人角色定妆图，服装、气质与身份明确，人物完整，便于后续复用。")
        return "；".join(prompt_segments)

    def generate_character_assets(
        self,
        project_bundle: SproutProjectBundle,
        *,
        output_root: str | Path,
        extra_reference_count: int = 0,
        skip_existing: bool = True,
    ) -> SproutProjectBundle:
        """为项目中的角色生成参考图。"""

        character_root = ensure_directory(Path(output_root) / "characters")
        for character in project_bundle.characters:
            self.generate_single_character_assets(
                character=character,
                output_root=character_root,
                visual_style=project_bundle.episode.visual_style,
                extra_reference_count=extra_reference_count,
                skip_existing=skip_existing,
            )
            for asset in character.reference_assets:
                project_bundle.register_asset(asset)
        project_bundle.ensure_manifest(output_root=str(Path(output_root)))
        return project_bundle

    def generate_single_character_assets(
        self,
        *,
        character: SproutCharacter,
        output_root: str | Path,
        visual_style: str | None = None,
        extra_reference_count: int = 0,
        skip_existing: bool = True,
    ) -> list[SproutAsset]:
        """生成单个角色的角色图。"""

        if skip_existing and self._has_usable_assets(character.reference_assets):
            return character.reference_assets

        image_client = self._get_image_client()
        character_output_dir = ensure_directory(Path(output_root) / character.character_id)
        prompt = self.build_character_prompt(character, visual_style=visual_style)

        anchor_path = image_client.generate_and_save_single(
            prompt=prompt,
            output_dir=character_output_dir,
            file_name_prefix=f"{character.character_id}_anchor",
        )
        anchor_asset = SproutAsset(
            asset_id=f"{character.character_id}_anchor",
            asset_type="character_anchor",
            source="seed_image",
            path=str(anchor_path),
            role="anchor",
            prompt=prompt,
            owner_id=character.character_id,
            metadata={"character_name": character.name},
        )

        generated_assets = [anchor_asset]
        if extra_reference_count > 0:
            extra_paths = image_client.generate_and_save(
                prompt=f"{prompt}；请保持同一人物设定，补充不同角度或不同表情的参考图。",
                output_dir=character_output_dir,
                reference_images=[str(anchor_path)],
                image_count=extra_reference_count,
                file_name_prefix=f"{character.character_id}_ref",
            )
            for index, extra_path in enumerate(extra_paths, start=1):
                generated_assets.append(
                    SproutAsset(
                        asset_id=f"{character.character_id}_ref_{index:02d}",
                        asset_type="character_reference",
                        source="seed_image",
                        path=str(extra_path),
                        role="reference_image",
                        prompt=prompt,
                        owner_id=character.character_id,
                        metadata={
                            "character_name": character.name,
                            "reference_index": index,
                        },
                    )
                )

        character.reference_assets = generated_assets
        return generated_assets

    def _has_usable_assets(self, assets: list[SproutAsset]) -> bool:
        if not assets:
            return False
        return all(asset.path and Path(asset.path).exists() for asset in assets)

    def _get_image_client(self) -> SeedImageClient:
        if self.image_client is None:
            self.image_client = SeedImageClient()
        return self.image_client
