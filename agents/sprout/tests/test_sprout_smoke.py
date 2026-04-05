"""Sprout 的离线冒烟测试。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agents.sprout import (
    SproutAsset,
    SproutExporter,
    SproutJimengPackager,
    SproutProjectBundle,
    SproutProjectStore,
    SproutShotPipeline,
    SproutTopicInput,
    SproutWorkflow,
)


def build_demo_bundle(root: Path) -> SproutProjectBundle:
    topic_input = SproutTopicInput(topic="古风逆袭短剧")
    bundle = SproutProjectBundle.from_planning_data(
        {
            "title": "测试项目",
            "core_hook": "重生复仇",
            "visual_style": "厚涂古风",
            "characters": [
                {
                    "name": "沈清辞",
                    "role": "女主",
                    "summary": "重生嫡女",
                    "appearance_prompt": "古风白衣女子",
                },
                {
                    "name": "沈清柔",
                    "role": "女配",
                    "summary": "伪善庶妹",
                    "appearance_prompt": "古风绿衣女子",
                },
            ],
            "shots": [
                {
                    "shot_index": 1,
                    "title": "冷宫重生",
                    "visual_description": "沈清辞在冷宫惊醒，眼神骤冷",
                    "dialogue": "这一次，我绝不认输",
                    "sound_effects": "冷风与衣料摩擦声",
                    "camera_language": "近景推进",
                    "emotion": "决绝",
                    "characters": ["沈清辞", "沈清柔"],
                }
            ],
        },
        topic_input=topic_input,
    )

    characters_root = root / "characters"
    characters_root.mkdir(parents=True, exist_ok=True)
    shen_path = characters_root / "shen.png"
    rou_path = characters_root / "rou.png"
    shen_path.write_text("shen", encoding="utf-8")
    rou_path.write_text("rou", encoding="utf-8")

    bundle.characters[0].reference_assets = [
        SproutAsset(
            asset_id="shen_anchor",
            asset_type="character_anchor",
            source="seed_image",
            path=str(shen_path),
        )
    ]
    bundle.characters[1].reference_assets = [
        SproutAsset(
            asset_id="rou_anchor",
            asset_type="character_anchor",
            source="seed_image",
            path=str(rou_path),
        )
    ]
    for character in bundle.characters:
        for asset in character.reference_assets:
            bundle.register_asset(asset)
    bundle.ensure_manifest(output_root=str(root))
    return bundle


class SproutSmokeTest(unittest.TestCase):
    def test_project_store_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            bundle = build_demo_bundle(root)
            store = SproutProjectStore()

            saved_path = store.save_bundle(bundle, output_root=root)
            loaded_bundle = store.load_bundle(saved_path)

            self.assertEqual(loaded_bundle.project_name, bundle.project_name)
            self.assertEqual(len(loaded_bundle.characters), 2)
            self.assertEqual(loaded_bundle.characters[0].name, "沈清辞")
            self.assertEqual(
                loaded_bundle.characters[0].reference_assets[0].path,
                bundle.characters[0].reference_assets[0].path,
            )

    def test_prepare_shot_builds_placeholder_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            bundle = build_demo_bundle(root)
            pipeline = SproutShotPipeline()

            shot = pipeline.prepare_shot(bundle, bundle.shots[0])

            self.assertEqual(shot.status, "prompt_ready")
            self.assertIn("[图1]", shot.video_prompt or "")
            self.assertIn("[图2]", shot.video_prompt or "")
            self.assertEqual(len(shot.reference_bindings), 2)

    def test_generate_shots_skips_existing_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            bundle = build_demo_bundle(root)
            videos_root = root / "videos"
            shots_root = root / "shots" / "shot_001"
            videos_root.mkdir(parents=True, exist_ok=True)
            shots_root.mkdir(parents=True, exist_ok=True)
            keyframe_path = shots_root / "shot_001_keyframe.png"
            video_path = videos_root / "shot_001.mp4"
            keyframe_path.write_text("keyframe", encoding="utf-8")
            video_path.write_text("video", encoding="utf-8")
            bundle.shots[0].output_assets = [
                SproutAsset(
                    asset_id="shot_001_keyframe",
                    asset_type="shot_keyframe",
                    source="seed_image",
                    path=str(keyframe_path),
                ),
                SproutAsset(
                    asset_id="shot_001_video_01",
                    asset_type="shot_video",
                    source="seed_video",
                    path=str(video_path),
                ),
            ]

            workflow = SproutWorkflow()
            workflow.generate_shots(
                project_bundle=bundle,
                output_root=root,
                shot_ids=["shot_001"],
            )

            self.assertEqual(bundle.shots[0].status, "generated")
            self.assertEqual(len(bundle.shots[0].output_assets), 2)

    def test_export_bundle_outputs_summary_and_card(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            bundle = build_demo_bundle(root)
            pipeline = SproutShotPipeline()
            shot = pipeline.prepare_shot(bundle, bundle.shots[0])
            packager = SproutJimengPackager()
            packager.build_cards(bundle)
            exporter = SproutExporter(jimeng_packager=packager)

            exported_paths = exporter.export_bundle(bundle, output_root=root)

            self.assertTrue(exported_paths["project_bundle_json"].exists())
            self.assertTrue(exported_paths["project_manifest_json"].exists())
            self.assertTrue(exported_paths["project_summary_md"].exists())
            self.assertTrue(
                exported_paths[f"workflow_card_{shot.shot_id}"].exists()
            )


if __name__ == "__main__":
    unittest.main()
