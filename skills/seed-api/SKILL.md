---
name: seed-api
description: 使用项目内 `module/api/seed/` 客户端完成字节 Seed 文本、多模态理解、生图、视频生成与本地下载。适用于用户要求调用、扩展、排查或测试 Seed LLM、Seedream、Seedance 接口，以及需要更新相关配置或文档时。
---

# Seed API

## 适用范围

当任务涉及以下内容时，优先使用本 Skill：

- 调用 `SeedLLMClient`
- 调用 `SeedImageClient`
- 调用 `SeedVideoClient`
- 调整 `config/seed_config.json`
- 检查 `config/seed_key.json` 与 `ARK_API_KEY`
- 排查 `image_to_group`、`i2v`、任务轮询、本地下载等 Seed 相关问题

## 代码位置

- 客户端目录：`module/api/seed/`
- 开发说明：`module/api/seed/readme.md`
- 公共参数配置：`config/seed_config.json`
- 私密密钥配置：`config/seed_key.json`

## 调用原则

1. 先判断能力类型：

- 文本/多模态理解：用 `SeedLLMClient`
- 生图：用 `SeedImageClient`
- 视频生成：用 `SeedVideoClient`

2. 默认优先使用项目内封装，不直接手写裸 `curl`，除非是在做协议排查。

3. 默认参数来自配置文件：

- `config/seed_config.json`：可提交，存放模型名、温度、尺寸、重试次数等
- `config/seed_key.json`：不可提交，存放 `api_key`

4. 调用时如果显式传参，显式参数优先于配置文件默认值。

## LLM 用法

使用 `messages` 模式，不再使用单轮快捷参数。

常用方法：

- `generate_response(messages, **extra_body)`
- `generate_text(messages, **extra_body)`

图片输入支持：

- `image_url`
- `image_path`
- `image_base64` + `mime_type`

## 生图用法

常用方法：

- `generate(...)`
- `generate_image_urls(...)`
- `generate_single_image_url(...)`
- `generate_and_save(...)`
- `generate_and_save_single(...)`

参考图支持：

- URL
- 本地路径
- Base64

### 组图补差规则

组图默认按剩余差值重试：

- 目标 5 张，首次返回 1 张，下一轮请求 4 张
- 若第二轮返回 2 张，下一轮请求 2 张

默认开启：

- `retry_on_partial`
- `strict_image_count`

如果最终仍未补齐，会直接报错。

### 已知问题

`image_to_group` 可能出现上游部分成功。

处理建议：

- 提示词显式写目标张数
- 提示词显式写每张图的分镜或物料拆分
- 必要时保留原始响应和重试轨迹

## 视频用法

常用方法：

- `create_task(...)`
- `create_text_to_video_task(...)`
- `create_image_to_video_task(...)`
- `get_task(task_id)`
- `wait_for_task(task_id, ...)`
- `create_image_to_video_and_wait(...)`
- `save_videos(...)`
- `save_videos_from_response(...)`
- `create_image_to_video_and_save(...)`

### 图生视频默认规则

图生视频默认使用：

- `image_role="first_frame"`
- `task_type="i2v"`

不要默认用 `reference_image` 触发图生视频，否则部分模型可能被识别成非预期任务类型。

## 工作流程

### 新增或修改 Seed 能力时

1. 先查看 `module/api/seed/readme.md`
2. 优先复用已有客户端结构和命名
3. 涉及默认参数时同步更新 `config/seed_config.json`
4. 涉及密钥读取时保持 `seed_key.json` 约定不变
5. 改动完成后做最少一轮真实或本地验证
6. 如有重要结论，同步更新 `readme`、`doc`、`wiki`

### 排查问题时

1. 先确认是上游接口问题还是本地封装问题
2. 保留请求体、原始响应、任务状态或下载结果
3. 若是组图/视频任务，优先检查：

- 返回数量是否不足
- 任务状态是否终态
- 参数是否被错误分类

## 附加资料

- 使用示例见 [examples.md](examples.md)
- 开发说明见 [../../module/api/seed/readme.md](../../module/api/seed/readme.md)
