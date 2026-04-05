"""Sprout 即梦执行卡封装。"""

from __future__ import annotations

from dataclasses import dataclass

from .schema import SproutProjectBundle, SproutShot, SproutWorkflowCard


@dataclass
class SproutJimengPackager:
    """负责输出网页端和手工备用执行卡。"""

    def build_card_for_shot(self, shot: SproutShot) -> SproutWorkflowCard:
        upload_sequence: list[str] = []
        placeholder_mapping: list[str] = []
        for binding in shot.reference_bindings:
            upload_sequence.append(
                f"{binding.placeholder} -> {binding.asset_path or '待上传'}"
            )
            binding_label = binding.character_name or binding.usage or "参考图"
            placeholder_mapping.append(f"{binding.placeholder} -> {binding_label}")

        notes = shot.notes or ""
        if shot.reference_bindings:
            notes = (
                f"{notes}\nAPI 调用时请保持上传顺序与占位符编号一致。".strip()
            )

        fallback_prompt = shot.video_prompt or shot.keyframe_prompt
        return SproutWorkflowCard(
            card_id=f"{shot.shot_id}_workflow_card",
            shot_id=shot.shot_id,
            title=shot.title,
            duration_seconds=shot.duration_seconds,
            upload_sequence=upload_sequence,
            placeholder_mapping=placeholder_mapping,
            api_prompt=shot.video_prompt,
            fallback_prompt=fallback_prompt,
            dialogue=shot.dialogue,
            sound_effects=shot.sound_effects,
            notes=notes or None,
        )

    def build_cards(self, project_bundle: SproutProjectBundle) -> list[SproutWorkflowCard]:
        workflow_cards = [self.build_card_for_shot(shot) for shot in project_bundle.shots]
        project_bundle.workflow_cards = workflow_cards
        project_bundle.ensure_manifest()
        return workflow_cards

    def render_card_markdown(self, workflow_card: SproutWorkflowCard) -> str:
        upload_lines = "\n".join(
            f"- {line}" for line in workflow_card.upload_sequence
        ) or "- 无"
        mapping_lines = "\n".join(
            f"- {line}" for line in workflow_card.placeholder_mapping
        ) or "- 无"
        return (
            f"# {workflow_card.title}\n\n"
            f"- 镜头 ID：`{workflow_card.shot_id}`\n"
            f"- 建议时长：`{workflow_card.duration_seconds}` 秒\n"
            f"- 台词：{workflow_card.dialogue or '无'}\n"
            f"- 音效：{workflow_card.sound_effects or '无'}\n\n"
            "## 上传顺序\n"
            f"{upload_lines}\n\n"
            "## 占位符映射\n"
            f"{mapping_lines}\n\n"
            "## API Prompt\n"
            f"{workflow_card.api_prompt or '无'}\n\n"
            "## 备用 Prompt\n"
            f"{workflow_card.fallback_prompt or '无'}\n\n"
            "## 备注\n"
            f"{workflow_card.notes or '无'}\n"
        )
