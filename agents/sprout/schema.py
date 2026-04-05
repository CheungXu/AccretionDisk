"""Sprout 项目数据结构。"""

from __future__ import annotations

from dataclasses import dataclass, field, is_dataclass
from pathlib import Path
from typing import Any

from .utils import slugify_name


def _serialize_value(value: Any) -> Any:
    if is_dataclass(value):
        return {
            key: _serialize_value(getattr(value, key))
            for key in value.__dataclass_fields__
        }
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, list):
        return [_serialize_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _serialize_value(item) for key, item in value.items()}
    return value


@dataclass
class SproutTopicInput:
    """Sprout 的主题输入。"""

    topic: str
    duration_seconds: int = 60
    shot_count: int = 10
    orientation: str = "9:16"
    visual_style: str | None = None
    target_audience: str | None = None
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _serialize_value(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SproutTopicInput":
        return cls(
            topic=str(payload.get("topic") or "").strip(),
            duration_seconds=int(payload.get("duration_seconds") or 60),
            shot_count=int(payload.get("shot_count") or 10),
            orientation=str(payload.get("orientation") or "9:16"),
            visual_style=_string_or_none(payload.get("visual_style")),
            target_audience=_string_or_none(payload.get("target_audience")),
            notes=_string_or_none(payload.get("notes")),
        )


@dataclass
class SproutEpisode:
    """单集短剧信息。"""

    episode_id: str
    title: str
    logline: str | None = None
    core_hook: str | None = None
    total_duration_seconds: int = 60
    target_shot_count: int = 10
    visual_style: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _serialize_value(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SproutEpisode":
        return cls(
            episode_id=str(payload.get("episode_id") or "").strip(),
            title=str(payload.get("title") or "").strip(),
            logline=_string_or_none(payload.get("logline")),
            core_hook=_string_or_none(payload.get("core_hook")),
            total_duration_seconds=int(payload.get("total_duration_seconds") or 60),
            target_shot_count=int(payload.get("target_shot_count") or 10),
            visual_style=_string_or_none(payload.get("visual_style")),
        )


@dataclass
class SproutAsset:
    """项目产物。"""

    asset_id: str
    asset_type: str
    source: str
    path: str | None = None
    url: str | None = None
    role: str | None = None
    prompt: str | None = None
    owner_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _serialize_value(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SproutAsset":
        return cls(
            asset_id=str(payload.get("asset_id") or "").strip(),
            asset_type=str(payload.get("asset_type") or "").strip(),
            source=str(payload.get("source") or "").strip(),
            path=_string_or_none(payload.get("path")),
            url=_string_or_none(payload.get("url")),
            role=_string_or_none(payload.get("role")),
            prompt=_string_or_none(payload.get("prompt")),
            owner_id=_string_or_none(payload.get("owner_id")),
            metadata=_coerce_dict(payload.get("metadata")),
        )


@dataclass
class SproutCharacter:
    """角色设定。"""

    character_id: str
    name: str
    role: str | None = None
    summary: str | None = None
    personality: str | None = None
    appearance: str | None = None
    appearance_prompt: str | None = None
    voice_style: str | None = None
    notes: str | None = None
    reference_assets: list[SproutAsset] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _serialize_value(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SproutCharacter":
        return cls(
            character_id=str(payload.get("character_id") or "").strip(),
            name=str(payload.get("name") or "").strip(),
            role=_string_or_none(payload.get("role")),
            summary=_string_or_none(payload.get("summary")),
            personality=_string_or_none(payload.get("personality")),
            appearance=_string_or_none(payload.get("appearance")),
            appearance_prompt=_string_or_none(payload.get("appearance_prompt")),
            voice_style=_string_or_none(payload.get("voice_style")),
            notes=_string_or_none(payload.get("notes")),
            reference_assets=[
                SproutAsset.from_dict(item)
                for item in _coerce_list(payload.get("reference_assets"))
                if isinstance(item, dict)
            ],
        )


@dataclass
class SproutReferenceBinding:
    """参考图绑定关系。"""

    binding_index: int
    placeholder: str
    asset_id: str
    asset_path: str | None = None
    character_id: str | None = None
    character_name: str | None = None
    usage: str | None = None
    prompt_fragment: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _serialize_value(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SproutReferenceBinding":
        return cls(
            binding_index=int(payload.get("binding_index") or 0),
            placeholder=str(payload.get("placeholder") or "").strip(),
            asset_id=str(payload.get("asset_id") or "").strip(),
            asset_path=_string_or_none(payload.get("asset_path")),
            character_id=_string_or_none(payload.get("character_id")),
            character_name=_string_or_none(payload.get("character_name")),
            usage=_string_or_none(payload.get("usage")),
            prompt_fragment=_string_or_none(payload.get("prompt_fragment")),
        )


@dataclass
class SproutShot:
    """单镜头分镜。"""

    shot_id: str
    shot_index: int
    title: str
    duration_seconds: int = 6
    visual_description: str | None = None
    dialogue: str | None = None
    sound_effects: str | None = None
    camera_language: str | None = None
    emotion: str | None = None
    characters: list[str] = field(default_factory=list)
    notes: str | None = None
    keyframe_prompt: str | None = None
    video_prompt: str | None = None
    prompt_options: dict[str, Any] = field(default_factory=dict)
    reference_bindings: list[SproutReferenceBinding] = field(default_factory=list)
    output_assets: list[SproutAsset] = field(default_factory=list)
    status: str = "pending"

    def to_dict(self) -> dict[str, Any]:
        return _serialize_value(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SproutShot":
        return cls(
            shot_id=str(payload.get("shot_id") or "").strip(),
            shot_index=int(payload.get("shot_index") or 0),
            title=str(payload.get("title") or "").strip(),
            duration_seconds=int(payload.get("duration_seconds") or 6),
            visual_description=_string_or_none(payload.get("visual_description")),
            dialogue=_string_or_none(payload.get("dialogue")),
            sound_effects=_string_or_none(payload.get("sound_effects")),
            camera_language=_string_or_none(payload.get("camera_language")),
            emotion=_string_or_none(payload.get("emotion")),
            characters=[
                str(item).strip()
                for item in _coerce_list(payload.get("characters"))
                if str(item).strip()
            ],
            notes=_string_or_none(payload.get("notes")),
            keyframe_prompt=_string_or_none(payload.get("keyframe_prompt")),
            video_prompt=_string_or_none(payload.get("video_prompt")),
            prompt_options=_coerce_dict(payload.get("prompt_options")),
            reference_bindings=[
                SproutReferenceBinding.from_dict(item)
                for item in _coerce_list(payload.get("reference_bindings"))
                if isinstance(item, dict)
            ],
            output_assets=[
                SproutAsset.from_dict(item)
                for item in _coerce_list(payload.get("output_assets"))
                if isinstance(item, dict)
            ],
            status=str(payload.get("status") or "pending"),
        )


@dataclass
class SproutWorkflowCard:
    """网页端或手工备用执行卡。"""

    card_id: str
    shot_id: str
    title: str
    duration_seconds: int
    upload_sequence: list[str] = field(default_factory=list)
    placeholder_mapping: list[str] = field(default_factory=list)
    api_prompt: str | None = None
    fallback_prompt: str | None = None
    dialogue: str | None = None
    sound_effects: str | None = None
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _serialize_value(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SproutWorkflowCard":
        return cls(
            card_id=str(payload.get("card_id") or "").strip(),
            shot_id=str(payload.get("shot_id") or "").strip(),
            title=str(payload.get("title") or "").strip(),
            duration_seconds=int(payload.get("duration_seconds") or 0),
            upload_sequence=[
                str(item).strip()
                for item in _coerce_list(payload.get("upload_sequence"))
                if str(item).strip()
            ],
            placeholder_mapping=[
                str(item).strip()
                for item in _coerce_list(payload.get("placeholder_mapping"))
                if str(item).strip()
            ],
            api_prompt=_string_or_none(payload.get("api_prompt")),
            fallback_prompt=_string_or_none(payload.get("fallback_prompt")),
            dialogue=_string_or_none(payload.get("dialogue")),
            sound_effects=_string_or_none(payload.get("sound_effects")),
            notes=_string_or_none(payload.get("notes")),
        )


@dataclass
class SproutManifest:
    """项目交接清单。"""

    project_id: str
    project_name: str
    title: str
    topic: str
    output_root: str | None = None
    total_characters: int = 0
    total_shots: int = 0
    generated_character_assets: int = 0
    generated_shot_assets: int = 0
    generated_workflow_cards: int = 0
    status: str = "draft"
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _serialize_value(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SproutManifest":
        return cls(
            project_id=str(payload.get("project_id") or "").strip(),
            project_name=str(payload.get("project_name") or "").strip(),
            title=str(payload.get("title") or "").strip(),
            topic=str(payload.get("topic") or "").strip(),
            output_root=_string_or_none(payload.get("output_root")),
            total_characters=int(payload.get("total_characters") or 0),
            total_shots=int(payload.get("total_shots") or 0),
            generated_character_assets=int(payload.get("generated_character_assets") or 0),
            generated_shot_assets=int(payload.get("generated_shot_assets") or 0),
            generated_workflow_cards=int(payload.get("generated_workflow_cards") or 0),
            status=str(payload.get("status") or "draft"),
            notes=[
                str(item).strip()
                for item in _coerce_list(payload.get("notes"))
                if str(item).strip()
            ],
        )


@dataclass
class SproutProjectBundle:
    """Sprout 项目整包。"""

    project_id: str
    project_name: str
    topic_input: SproutTopicInput
    episode: SproutEpisode
    characters: list[SproutCharacter] = field(default_factory=list)
    shots: list[SproutShot] = field(default_factory=list)
    workflow_cards: list[SproutWorkflowCard] = field(default_factory=list)
    assets: list[SproutAsset] = field(default_factory=list)
    manifest: SproutManifest | None = None
    source_storyboard: str | None = None
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = _serialize_value(self)
        if self.manifest is None:
            payload["manifest"] = None
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SproutProjectBundle":
        manifest_payload = payload.get("manifest")
        project_bundle = cls(
            project_id=str(payload.get("project_id") or "").strip(),
            project_name=str(payload.get("project_name") or "").strip(),
            topic_input=SproutTopicInput.from_dict(_coerce_dict(payload.get("topic_input"))),
            episode=SproutEpisode.from_dict(_coerce_dict(payload.get("episode"))),
            characters=[
                SproutCharacter.from_dict(item)
                for item in _coerce_list(payload.get("characters"))
                if isinstance(item, dict)
            ],
            shots=[
                SproutShot.from_dict(item)
                for item in _coerce_list(payload.get("shots"))
                if isinstance(item, dict)
            ],
            workflow_cards=[
                SproutWorkflowCard.from_dict(item)
                for item in _coerce_list(payload.get("workflow_cards"))
                if isinstance(item, dict)
            ],
            assets=[
                SproutAsset.from_dict(item)
                for item in _coerce_list(payload.get("assets"))
                if isinstance(item, dict)
            ],
            manifest=(
                SproutManifest.from_dict(manifest_payload)
                if isinstance(manifest_payload, dict)
                else None
            ),
            source_storyboard=_string_or_none(payload.get("source_storyboard")),
            notes=[
                str(item).strip()
                for item in _coerce_list(payload.get("notes"))
                if str(item).strip()
            ],
        )
        project_bundle.shots = sorted(project_bundle.shots, key=lambda shot: shot.shot_index)
        return project_bundle

    def find_character(self, name_or_id: str) -> SproutCharacter | None:
        normalized_value = name_or_id.strip().lower()
        for character in self.characters:
            if character.character_id == normalized_value:
                return character
            if character.name.strip().lower() == normalized_value:
                return character
        return None

    def find_shot(self, shot_id: str) -> SproutShot | None:
        normalized_value = shot_id.strip().lower()
        for shot in self.shots:
            if shot.shot_id == normalized_value:
                return shot
        return None

    def register_asset(self, asset: SproutAsset) -> None:
        if any(existing.asset_id == asset.asset_id for existing in self.assets):
            return
        self.assets.append(asset)

    def ensure_manifest(self, *, output_root: str | None = None) -> SproutManifest:
        if self.manifest is None:
            self.manifest = SproutManifest(
                project_id=self.project_id,
                project_name=self.project_name,
                title=self.episode.title,
                topic=self.topic_input.topic,
                output_root=output_root,
                total_characters=len(self.characters),
                total_shots=len(self.shots),
            )
        if output_root is not None:
            self.manifest.output_root = output_root
        self.manifest.total_characters = len(self.characters)
        self.manifest.total_shots = len(self.shots)
        self.manifest.generated_character_assets = sum(
            len(character.reference_assets) for character in self.characters
        )
        self.manifest.generated_shot_assets = sum(
            len(shot.output_assets) for shot in self.shots
        )
        self.manifest.generated_workflow_cards = len(self.workflow_cards)
        return self.manifest

    @classmethod
    def from_planning_data(
        cls,
        planning_data: dict[str, Any],
        *,
        topic_input: SproutTopicInput,
        project_name: str | None = None,
        source_storyboard: str | None = None,
    ) -> "SproutProjectBundle":
        title = str(planning_data.get("title") or topic_input.topic).strip()
        project_name = project_name or slugify_name(title, default_prefix="sprout_project")
        episode = SproutEpisode(
            episode_id=f"{project_name}_episode_01",
            title=title,
            logline=_string_or_none(planning_data.get("logline")),
            core_hook=_string_or_none(planning_data.get("core_hook")),
            total_duration_seconds=int(
                planning_data.get("total_duration_seconds") or topic_input.duration_seconds
            ),
            target_shot_count=int(
                planning_data.get("shot_count") or topic_input.shot_count
            ),
            visual_style=_string_or_none(
                planning_data.get("visual_style") or topic_input.visual_style
            ),
        )

        characters: list[SproutCharacter] = []
        for index, item in enumerate(_coerce_list(planning_data.get("characters")), start=1):
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or f"角色{index}").strip()
            character_id = slugify_name(
                str(item.get("character_id") or name),
                default_prefix=f"character_{index}",
            )
            characters.append(
                SproutCharacter(
                    character_id=character_id,
                    name=name,
                    role=_string_or_none(item.get("role")),
                    summary=_string_or_none(item.get("summary")),
                    personality=_string_or_none(item.get("personality")),
                    appearance=_string_or_none(item.get("appearance")),
                    appearance_prompt=_string_or_none(item.get("appearance_prompt")),
                    voice_style=_string_or_none(item.get("voice_style")),
                    notes=_string_or_none(item.get("notes")),
                )
            )

        shots: list[SproutShot] = []
        default_shot_duration = max(
            int(topic_input.duration_seconds / max(topic_input.shot_count, 1)),
            1,
        )
        for index, item in enumerate(_coerce_list(planning_data.get("shots")), start=1):
            if not isinstance(item, dict):
                continue
            shot_index = int(item.get("shot_index") or index)
            shots.append(
                SproutShot(
                    shot_id=slugify_name(
                        str(item.get("shot_id") or f"shot_{shot_index:03d}"),
                        default_prefix=f"shot_{shot_index:03d}",
                    ),
                    shot_index=shot_index,
                    title=str(item.get("title") or f"镜头{shot_index}").strip(),
                    duration_seconds=int(item.get("duration_seconds") or default_shot_duration),
                    visual_description=_string_or_none(item.get("visual_description")),
                    dialogue=_string_or_none(item.get("dialogue")),
                    sound_effects=_string_or_none(item.get("sound_effects")),
                    camera_language=_string_or_none(item.get("camera_language")),
                    emotion=_string_or_none(item.get("emotion")),
                    characters=[
                        str(name).strip()
                        for name in _coerce_list(item.get("characters"))
                        if str(name).strip()
                    ],
                    notes=_string_or_none(item.get("notes")),
                )
            )

        project_bundle = cls(
            project_id=f"{project_name}_bundle",
            project_name=project_name,
            topic_input=topic_input,
            episode=episode,
            characters=characters,
            shots=sorted(shots, key=lambda shot: shot.shot_index),
            source_storyboard=source_storyboard,
        )
        project_bundle.ensure_manifest()
        return project_bundle


def _coerce_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _coerce_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    normalized_value = str(value).strip()
    return normalized_value or None
