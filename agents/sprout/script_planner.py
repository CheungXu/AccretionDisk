"""Sprout 剧本规划器。"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

from module.api.seed import SeedLLMClient

from .schema import SproutProjectBundle, SproutTopicInput
from .utils import load_json_text


PLANNING_SCHEMA_EXAMPLE = {
    "title": "竖屏短剧标题",
    "logline": "一句话剧情概述",
    "core_hook": "最吸引人的爽点或冲突",
    "visual_style": "整体视觉风格",
    "total_duration_seconds": 60,
    "shot_count": 10,
    "characters": [
        {
            "name": "角色名",
            "role": "角色定位",
            "summary": "角色一句话简介",
            "personality": "性格关键词",
            "appearance": "外形描述",
            "appearance_prompt": "可直接用于生图的角色描述",
            "voice_style": "台词语气",
            "notes": "补充说明",
        }
    ],
    "shots": [
        {
            "shot_index": 1,
            "title": "镜头标题",
            "duration_seconds": 6,
            "visual_description": "镜头画面描述",
            "dialogue": "镜头台词，没有就写空字符串",
            "sound_effects": "音效或环境声",
            "camera_language": "机位、景别、运动方式",
            "emotion": "情绪与戏剧目标",
            "characters": ["角色名1", "角色名2"],
            "notes": "补充制作备注",
        }
    ],
}


@dataclass
class SproutScriptPlanner:
    """负责将主题或分镜整理为结构化项目包。"""

    llm_client: SeedLLMClient | None = None
    default_temperature: float = 0.8
    llm_timeout_seconds: int = 180
    max_retries: int = 2
    retry_backoff_seconds: int = 3

    def plan_from_topic(
        self,
        topic_input: SproutTopicInput | str,
        *,
        project_name: str | None = None,
    ) -> SproutProjectBundle:
        """从一句题材生成结构化项目包。"""

        resolved_input = self._normalize_topic_input(topic_input)
        prompt = self._build_topic_prompt(resolved_input)
        planning_data = self._request_planning_json(prompt)
        return self._build_bundle(
            planning_data,
            topic_input=resolved_input,
            project_name=project_name,
        )

    def plan_from_storyboard(
        self,
        storyboard_text: str,
        *,
        topic_input: SproutTopicInput | None = None,
        project_name: str | None = None,
    ) -> SproutProjectBundle:
        """将已有分镜整理为结构化项目包。"""

        if not storyboard_text.strip():
            raise ValueError("storyboard_text 不能为空。")
        resolved_input = topic_input or SproutTopicInput(topic="已有分镜整理")
        prompt = self._build_storyboard_prompt(
            storyboard_text=storyboard_text,
            topic_input=resolved_input,
        )
        planning_data = self._request_planning_json(prompt)
        return self._build_bundle(
            planning_data,
            topic_input=resolved_input,
            project_name=project_name,
            source_storyboard=storyboard_text,
        )

    def _build_bundle(
        self,
        planning_data: dict[str, Any],
        *,
        topic_input: SproutTopicInput,
        project_name: str | None = None,
        source_storyboard: str | None = None,
    ) -> SproutProjectBundle:
        project_bundle = SproutProjectBundle.from_planning_data(
            planning_data,
            topic_input=topic_input,
            project_name=project_name,
            source_storyboard=source_storyboard,
        )
        if not project_bundle.characters:
            raise ValueError("模型输出中缺少角色信息。")
        if not project_bundle.shots:
            raise ValueError("模型输出中缺少镜头信息。")
        return project_bundle

    def _request_planning_json(self, user_prompt: str) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 2):
            try:
                llm_client = self._get_llm_client()
                response_text = llm_client.generate_text(
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "你是 AI 短剧策划助手。"
                                "你必须严格输出 JSON，不要输出 Markdown、解释、补充说明或代码围栏。"
                                "输出内容必须可被 json.loads 直接解析。"
                            ),
                        },
                        {
                            "role": "user",
                            "content": user_prompt,
                        },
                    ],
                    temperature=self.default_temperature,
                )
                parsed_payload = load_json_text(response_text)
                if not isinstance(parsed_payload, dict):
                    raise ValueError("模型输出不是对象类型 JSON。")
                return parsed_payload
            except Exception as exc:
                last_error = exc
                if not self._is_retryable_error(exc) or attempt > self.max_retries:
                    raise
                self.llm_client = None
                time.sleep(self.retry_backoff_seconds * attempt)

        if last_error is not None:
            raise last_error
        raise RuntimeError("未能获取剧本规划结果。")

    def _build_topic_prompt(self, topic_input: SproutTopicInput) -> str:
        return (
            "请将下面的题材扩写为可直接进入 AI 短剧生产的结构化策划。\n"
            f"题材：{topic_input.topic}\n"
            f"总时长：{topic_input.duration_seconds} 秒\n"
            f"目标镜头数：{topic_input.shot_count}\n"
            f"画幅：{topic_input.orientation}\n"
            f"视觉风格偏好：{topic_input.visual_style or '未指定，请自行补全'}\n"
            f"目标受众：{topic_input.target_audience or '未指定'}\n"
            f"补充说明：{topic_input.notes or '无'}\n\n"
            "请重点补齐：\n"
            "1. 爽点明确、适合竖屏快节奏传播\n"
            "2. 角色设定能直接用于后续生图\n"
            "3. 每个镜头都包含画面、台词、音效、机位、情绪\n"
            "4. 镜头时长总和尽量接近总时长\n\n"
            "请严格按下面 JSON 结构输出：\n"
            f"{json.dumps(PLANNING_SCHEMA_EXAMPLE, ensure_ascii=False, indent=2)}"
        )

    def _build_storyboard_prompt(
        self,
        *,
        storyboard_text: str,
        topic_input: SproutTopicInput,
    ) -> str:
        return (
            "请将下面已有的分镜脚本整理成统一的短剧项目 JSON。"
            "尽量保留原有剧情内容，不要擅自重写核心冲突。\n"
            f"预期总时长：{topic_input.duration_seconds} 秒\n"
            f"预期镜头数：{topic_input.shot_count}\n"
            f"画幅：{topic_input.orientation}\n"
            f"视觉风格偏好：{topic_input.visual_style or '未指定'}\n"
            f"补充说明：{topic_input.notes or '无'}\n\n"
            "已有分镜内容如下：\n"
            f"{storyboard_text}\n\n"
            "请按下面 JSON 结构输出，字段缺失时请合理补齐：\n"
            f"{json.dumps(PLANNING_SCHEMA_EXAMPLE, ensure_ascii=False, indent=2)}"
        )

    def _normalize_topic_input(self, topic_input: SproutTopicInput | str) -> SproutTopicInput:
        if isinstance(topic_input, SproutTopicInput):
            return topic_input
        if isinstance(topic_input, str) and topic_input.strip():
            return SproutTopicInput(topic=topic_input.strip())
        raise ValueError("topic_input 必须是非空字符串或 SproutTopicInput。")

    def _get_llm_client(self) -> SeedLLMClient:
        if self.llm_client is None:
            self.llm_client = SeedLLMClient(timeout=self.llm_timeout_seconds)
        return self.llm_client

    @staticmethod
    def _is_retryable_error(exc: Exception) -> bool:
        message = str(exc).lower()
        retryable_keywords = [
            "timed out",
            "timeout",
            "temporarily unavailable",
            "connection reset",
            "network",
            "remote end closed connection",
        ]
        return isinstance(exc, TimeoutError) or any(keyword in message for keyword in retryable_keywords)
