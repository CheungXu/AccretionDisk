# Sprout 项目启动记录

## 背景

本轮工作计划在 `agents/sprout/` 建立一个面向 AI 短剧的萌芽项目，用于复现“豆包写剧本 + Seed 生图 + Seedance 生视频”的核心工作流。

## 本次确认的信息

- 文章方法已经明确：先剧本、后角色、再逐镜头生成
- 当前仓库已具备 `SeedLLMClient`、`SeedImageClient`、`SeedVideoClient` 三条基础能力
- 视频链路支持 `generate_audio`
- 多图参考绑定需要与官方文档对齐，采用 `"[图1] ... [图2] ..."` 这种写法

## 一期范围

- 从一句题材生成可继续生产的短剧项目包
- 生成角色参考图
- 生成至少一个镜头的有声视频
- 输出镜头清单和即梦执行卡

## 当前落位

本次已完成项目文档与代码骨架初始化：

- `agents/sprout/plan.md`
- `agents/sprout/readme.md`
- `agents/sprout/schema.py`
- `agents/sprout/script_planner.py`
- `agents/sprout/character_builder.py`
- `agents/sprout/shot_pipeline.py`
- `agents/sprout/jimeng_packager.py`
- `agents/sprout/exporter.py`
- `agents/sprout/workflow.py`
- `agents/sprout/run.py`
- `data/sprout/readme.md`
- `wiki/sprout/short-drama-workflow.md`

## 当前能力

当前已支持两类调用方式：

1. 整体链路调用：一句题材或已有分镜直接走到角色图、镜头 prompt、部分视频生成与导出
2. 单节点调用：可分别执行分镜规划、角色生图、镜头 prompt 准备、镜头视频生成、执行卡生成、项目导出

当前命令行已支持：

- `plan-topic`
- `plan-storyboard`
- `build-characters`
- `prepare-shots`
- `generate-shots`
- `build-cards`
- `export`
- `run-all`

## 当前验证

已完成：

- Python 模块编译检查
- 离线 bundle 读写回放
- 单节点命令离线调用验证
- `[图N]` 绑定 prompt 生成验证
- `unittest` 离线冒烟测试

## 真实链路测试结论

已按单节点顺序完成真实调用验证：

1. `plan-topic`
2. `build-characters`
3. `prepare-shots`
4. `generate-shots`
5. `build-cards`
6. `export`

本轮真实测试发现并已处理的问题：

- `plan-topic` 首次调用会因 LLM 默认 `60s` 读取超时失败
- `generate-shots` 在多参考图场景下，当前默认 `Seedance 1.5 Pro` 不兼容
- 当前账号环境下，`doubao-seedance-2-0-fast` 与 `doubao-seedance-2-0` 都返回无权限或模型不存在

当前已采取的工程措施：

- `script_planner` 增加更长超时与重试
- `shot_pipeline` 改为多参考图请求不再混用 `first_frame` 与 `reference_image`
- 若账号没有 `Seedance 2.0` 多参考图权限，则自动回退为“多图生成关键帧 + 单图图生视频”
- CLI 已支持手动覆盖视频模型名，便于后续在不同账号环境下测试

## 后续重点

1. 定义统一数据结构
2. 接入剧本规划
3. 接入角色生图
4. 接入镜头级视频生成
5. 补齐导出清单和交接信息
