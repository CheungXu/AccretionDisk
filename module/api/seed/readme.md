# Seed API 模块说明

## 模块概览

`module/api/seed/` 当前包含两个客户端：

- `llm.py`：字节 Seed 文本与多模态理解接口
- `image.py`：字节 Seed 生图接口
- `video.py`：字节 Seed 视频生成接口

统一目标：

- 不在代码中明文硬编码 API Key
- 尽量统一输入结构
- 为后续扩展更多 Seed 能力预留一致的调用习惯

## API Key 配置

读取顺序如下：

1. 环境变量 `ARK_API_KEY`
2. 配置文件 `config/seed_key.json`

配置文件示例：

密钥配置示例：

```json
{
  "api_key": "your-api-key"
}
```

## 公共参数配置

除密钥外，Seed 模块的默认模型参数统一从 `config/seed_config.json` 读取。

当前按三类能力拆分：

- `llm`
- `image`
- `video`

示例结构：

```json
{
  "llm": {
    "model_name": "doubao-seed-2-0-pro-260215",
    "default_request_options": {
      "temperature": 0.7,
      "top_p": 0.95
    }
  },
  "image": {
    "model_name": "doubao-seedream-5-0-260128",
    "response_format": "url",
    "size": "2K"
  },
  "video": {
    "model_name": "doubao-seedance-1-5-pro-251215",
    "task_type": "i2v",
    "image_role": "first_frame",
    "generate_audio": true,
    "default_prompt_options": {
      "duration": 5,
      "camerafixed": false,
      "watermark": true
    }
  }
}
```

约定：

- `config/seed_key.json`：本地私密配置，用于 API Key
- `config/seed_config.json`：可提交的公共默认参数配置

本次配置收敛后，三个客户端都遵循同一规则：

- 密钥默认从 `config/seed_key.json` 读取
- 模型参数默认从 `config/seed_config.json` 读取
- 调用时显式传入的参数优先级高于配置文件

## 文本与多模态接口

主类：`SeedLLMClient`

### 主要方法

- `generate_response(messages, **extra_body)`：返回原始响应
- `generate_text(messages, **extra_body)`：直接提取文本结果

默认情况下，`temperature`、`top_p` 等请求参数会从 `config/seed_config.json` 的 `llm.default_request_options` 读取；调用时显式传入的参数优先级更高。

### 消息结构

统一使用 `messages` 传参，结构与多轮对话保持一致：

```python
messages = [
    {"role": "system", "content": "你是一个简洁的中文助手。"},
    {
        "role": "user",
        "content": [
            {"type": "input_image", "image_url": "https://example.com/demo.png"},
            {"type": "input_text", "text": "请描述图片内容。"},
        ],
    },
]
```

### 图片输入支持

图片内容块支持以下三类输入：

- `image_url`
- `image_path`
- `image_base64` + `mime_type`

本地图片与 Base64 会在客户端内部自动规范化为可提交格式。

## 生图接口

主类：`SeedImageClient`

### 主要方法

- `generate(...)`：返回原始接口结果
- `generate_image_urls(...)`：提取图片 URL 列表
- `generate_single_image_url(...)`：获取单张图片 URL
- `generate_and_save(...)`：生成后批量保存到本地
- `generate_and_save_single(...)`：生成单张并保存到本地
- `save_images(...)`：将已有 URL 下载到本地

### 适用场景

支持：

- 文生图
- 图生图
- 单图生成
- 组图生成
- 本地保存

参考图输入支持：

- 图片 URL
- 本地图片路径
- Base64 图片内容

### 推荐调用方式

单张生成：

```python
from module.api.seed import SeedImageClient

client = SeedImageClient()
image_url = client.generate_single_image_url(
    prompt="生成一张赛博朋克城市夜景海报"
)
```

组图并保存：

```python
from module.api.seed import SeedImageClient

client = SeedImageClient()
saved_paths = client.generate_and_save(
    prompt="生成4张同主题插画，分别表现春夏秋冬",
    output_dir="tmp/seed_output",
    image_count=4,
)
```

图生组图：

```python
from module.api.seed import SeedImageClient

client = SeedImageClient()
image_urls = client.generate_image_urls(
    prompt="生成5张品牌视觉延展图，分别展示不同物料",
    reference_images=["https://example.com/logo.png"],
    image_count=5,
)
```

## 组图补差重试

组图默认开启按差值重试：

- 目标 5 张，首轮返回 1 张，则下一轮请求剩余 4 张
- 若再返回 2 张，则下一轮请求剩余 2 张

相关参数：

- `retry_on_partial=True`
- `max_partial_retries=3`
- `strict_image_count=True`

默认行为：

- 若多轮后仍未补齐目标张数，抛出异常
- 避免业务侧误把少图结果当作完整成功

以上默认值也可通过 `config/seed_config.json` 的 `image` 分组配置。

## 已知限制

当前已观察到 `image_to_group` 场景会出现上游部分成功：

- 某些单参考图提示词下，请求的组图数量可能无法全部返回
- 即使客户端已补差重试，也可能在多轮后仍未补齐

建议在提示词中显式写明：

- 目标张数
- 每张图的分镜或物料拆分
- 稳定的品牌、颜色、风格约束

## 视频接口

主类：`SeedVideoClient`

### 主要方法

- `create_task(...)`：创建通用视频任务
- `create_text_to_video_task(...)`：创建文生视频任务
- `create_image_to_video_task(...)`：创建图生视频任务
- `get_task(task_id)`：查询任务
- `wait_for_task(task_id, ...)`：轮询等待任务完成
- `create_and_wait(...)`：创建并等待完成
- `create_image_to_video_and_wait(...)`：图生视频创建并等待完成
- `save_videos(...)`：下载视频 URL 到本地
- `save_videos_from_response(...)`：从任务结果中提取并下载视频
- `create_image_to_video_and_save(...)`：图生视频创建、等待完成并保存到本地

### 图生视频默认行为

图生视频默认使用：

- `image_role="first_frame"`
- `task_type="i2v"`

这样可以避免部分模型把任务误判为 `r2v`。

视频相关默认值同样从 `config/seed_config.json` 的 `video` 分组读取，包括：

- `model_name`
- `task_type`
- `image_role`
- `generate_audio`
- `poll_interval_seconds`
- `wait_timeout_seconds`
- `default_prompt_options`

其中：

- `generate_audio=true`：默认生成有声视频
- `generate_audio=false`：默认生成无声视频
- 调用时显式传入 `generate_audio` 会覆盖配置文件默认值

### 推荐调用方式

图生视频：

```python
from module.api.seed import SeedVideoClient

client = SeedVideoClient()
task = client.create_image_to_video_task(
    prompt="无人机高速穿越峡谷，带来沉浸式飞行体验",
    image_input="https://example.com/demo.png",
    prompt_options={
        "duration": 5,
        "camerafixed": False,
        "watermark": True,
    },
)
```

图生视频并保存：

```python
from module.api.seed import SeedVideoClient

client = SeedVideoClient()
saved_paths = client.create_image_to_video_and_save(
    prompt="无人机高速穿越峡谷，带来沉浸式飞行体验",
    image_input="https://example.com/demo.png",
    output_dir="tmp/seed_video_output",
    prompt_options={
        "duration": 5,
        "camerafixed": False,
        "watermark": True,
    },
    file_name="demo.mp4",
)
```

### 视频下载说明

视频下载方法支持：

- 直接传入视频 URL 列表下载
- 从最终任务响应中提取视频 URL 后下载

默认会根据响应头或 URL 推断扩展名，无法推断时回退为 `.mp4`。
