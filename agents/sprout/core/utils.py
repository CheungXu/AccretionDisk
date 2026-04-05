"""Sprout 核心通用工具。"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def slugify_name(value: str, *, default_prefix: str = "item") -> str:
    """将展示名称转换为稳定标识。"""

    normalized_value = re.sub(r"\s+", "_", value.strip(), flags=re.UNICODE)
    normalized_value = re.sub(r"[^\w\-]+", "_", normalized_value, flags=re.UNICODE)
    normalized_value = normalized_value.strip("_").lower()
    if normalized_value:
        return normalized_value[:80]
    return default_prefix


def ensure_directory(path: str | Path) -> Path:
    """确保目录存在。"""

    directory = Path(path).expanduser()
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def write_json_file(path: str | Path, payload: Any) -> Path:
    """将对象按 JSON 写入文件。"""

    output_path = Path(path).expanduser()
    ensure_directory(output_path.parent)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output_path


def read_json_file(path: str | Path) -> Any:
    """读取 JSON 文件。"""

    input_path = Path(path).expanduser()
    return json.loads(input_path.read_text(encoding="utf-8"))


def write_text_file(path: str | Path, content: str) -> Path:
    """写入文本文件。"""

    output_path = Path(path).expanduser()
    ensure_directory(output_path.parent)
    output_path.write_text(content, encoding="utf-8")
    return output_path


def strip_markdown_code_fence(text: str) -> str:
    """去掉 Markdown 代码块包裹。"""

    stripped_text = text.strip()
    fenced_match = re.fullmatch(
        r"```(?:json|javascript|js|text)?\s*(.*?)```",
        stripped_text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    if fenced_match:
        return fenced_match.group(1).strip()
    return stripped_text


def _extract_balanced_block(text: str, open_char: str, close_char: str) -> str | None:
    start_index = text.find(open_char)
    if start_index < 0:
        return None

    depth = 0
    in_string = False
    escape_next = False
    for index in range(start_index, len(text)):
        current_char = text[index]
        if in_string:
            if escape_next:
                escape_next = False
                continue
            if current_char == "\\":
                escape_next = True
                continue
            if current_char == '"':
                in_string = False
            continue

        if current_char == '"':
            in_string = True
            continue
        if current_char == open_char:
            depth += 1
            continue
        if current_char == close_char:
            depth -= 1
            if depth == 0:
                return text[start_index : index + 1]
    return None


def extract_json_text(text: str) -> str:
    """从模型输出中提取 JSON 片段。"""

    stripped_text = strip_markdown_code_fence(text)
    if not stripped_text:
        raise ValueError("文本为空，无法提取 JSON。")

    object_text = _extract_balanced_block(stripped_text, "{", "}")
    array_text = _extract_balanced_block(stripped_text, "[", "]")
    candidates = [candidate for candidate in (object_text, array_text) if candidate]
    if not candidates:
        raise ValueError("未找到可解析的 JSON 片段。")

    candidates.sort(key=lambda item: stripped_text.find(item))
    return candidates[0]


def load_json_text(text: str) -> Any:
    """从模型文本中提取并解析 JSON。"""

    json_text = extract_json_text(text)
    return json.loads(json_text)
