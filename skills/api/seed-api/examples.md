# Seed API 示例

## 文本生成

```python
from module.api.seed import SeedLLMClient

client = SeedLLMClient()
messages = [
    {"role": "system", "content": "你是一个简洁的中文助手。"},
    {"role": "user", "content": "请用中文一句话介绍你的能力。"},
]
text = client.generate_text(messages)
print(text)
```

## 多模态理解

```python
from module.api.seed import SeedLLMClient

client = SeedLLMClient()
messages = [
    {
        "role": "user",
        "content": [
            {"type": "input_image", "image_url": "https://example.com/demo.png"},
            {"type": "input_text", "text": "请描述图片内容。"},
        ],
    }
]
text = client.generate_text(messages)
print(text)
```

## 生图并保存

```python
from module.api.seed import SeedImageClient

client = SeedImageClient()
saved_paths = client.generate_and_save(
    prompt="生成4张春夏秋冬主题插画",
    output_dir="tmp/seed_output",
    image_count=4,
)
print(saved_paths)
```

## 图生视频并保存

```python
from module.api.seed import SeedVideoClient

client = SeedVideoClient()
saved_paths = client.create_image_to_video_and_save(
    prompt="无人机高速穿越峡谷，带来沉浸式飞行体验",
    image_input="https://example.com/demo.png",
    reference_images=[
        "https://example.com/style_reference.png",
        "https://example.com/scene_reference.png",
    ],
    output_dir="tmp/seed_video_output",
)
print(saved_paths)
```

## 更新默认参数

优先修改 `config/seed_config.json`，不要把模型参数重新硬编码回客户端代码。

常见配置项：

- `llm.model_name`
- `llm.default_request_options.temperature`
- `image.size`
- `image.max_partial_retries`
- `video.task_type`
- `video.default_prompt_options`
