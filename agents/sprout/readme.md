# sprout

## 项目定位

`sprout` 是 `AccretionDisk` 中面向 AI 短剧的一期萌芽项目，用来复现“豆包写剧本 + Seed 生图 + Seedance 生视频”的生产链路，并把流程沉淀成后续可继续开发的 agent 项目。

当前重点：

- 从一句题材生成可生产的短剧方案
- 沉淀角色参考图与镜头级素材组织方式
- 对齐官方视频生成接口能力
- 对齐官方推荐的多图绑定 prompt 写法

## 当前阶段

当前已经具备一版可运行骨架，包括：

- 统一数据结构
- 一句话题材与已有分镜两种规划入口
- 角色图生成封装
- 镜头 prompt 准备与 `[图N]` 绑定
- 单镜头视频生成封装
- 即梦执行卡与项目导出能力
- 单节点命令与整体链路命令

## 核心方法

### 1. 剧本规划

- 输入可以是一句题材，也可以是已有分镜脚本
- 输出目标是标题、核心卖点、角色设定、镜头表、台词和生产备注

### 2. 角色资产

- 每个主角先生成定妆图
- 必要时补充多角度或多表情参考图
- 所有角色图都要有稳定命名和归档位置

### 3. 镜头生成

- 视频生成采用图生视频工作流
- 主图优先作为 `first_frame`
- 额外参考图统一按 `reference_image` 组织
- prompt 中使用官方推荐的 `"[图1] ... [图2] ..."` 绑定写法

### 4. 有声输出

- 视频链路默认按有声视频能力规划
- 每个镜头需要保留台词与音频备注，便于后续做 API 调用或人工复核

## 目录建议

### 代码

- `plan.md`：项目执行计划
- `schema.py` / `project_schema.py`：数据结构
- `script_planner.py`：剧本规划
- `character_builder.py`：角色资产生成
- `shot_pipeline.py`：镜头 prompt 与视频生成
- `jimeng_packager.py`：即梦执行卡
- `exporter.py`：项目导出
- `workflow.py`：整体编排
- `project_store.py`：bundle 持久化
- `run.py`：命令行入口

### 数据

数据建议写入 `data/sprout/`，并按项目维度继续拆分：

- `input/`
- `script/`
- `characters/`
- `shots/`
- `videos/`
- `workflow_cards/`
- `manifest/`

## 对齐依据

- 文章方法：先剧本、后角色、再逐镜头生成
- 当前仓库能力：`module/api/seed/llm.py`、`module/api/seed/image.py`、`module/api/seed/video.py`
- 官方接口约束：多图绑定采用 `"[图1] ... [图2] ..."`；有声视频通过 `generate_audio` 控制

## 后续开发重点

1. 定义统一数据结构和项目清单格式
2. 接入题材扩写与分镜结构化
3. 接入角色参考图生成
4. 接入镜头视频与官方绑定 prompt
5. 输出即梦执行卡与后期拼接清单

## 使用方式

### 整体链路

从一句题材直接跑到角色图、镜头 prompt、部分视频与导出：

```bash
python3 -m agents.sprout run-all \
  --topic "比较火的赘婿题材古风短剧" \
  --output-root "data/sprout/demo_project" \
  --project-name "sprout_demo" \
  --visual-style "国漫古风条漫，厚涂，高对比，高张力" \
  --extra-reference-count 1 \
  --generate-video-shot-count 1
```

### 单节点测试

先一句话生成结构化分镜：

```bash
python3 -m agents.sprout plan-topic \
  --topic "比较火的赘婿题材古风短剧" \
  --output-root "data/sprout/demo_project" \
  --project-name "sprout_demo"
```

再基于已有 bundle 生成人设图：

```bash
python3 -m agents.sprout build-characters \
  --bundle-file "data/sprout/demo_project/script/sprout_demo_bundle.json" \
  --output-root "data/sprout/demo_project" \
  --extra-reference-count 1
```

准备镜头 prompt 和 `[图N]` 绑定：

```bash
python3 -m agents.sprout prepare-shots \
  --bundle-file "data/sprout/demo_project/script/sprout_demo_bundle.json" \
  --output-root "data/sprout/demo_project"
```

只生成指定镜头：

```bash
python3 -m agents.sprout generate-shots \
  --bundle-file "data/sprout/demo_project/script/sprout_demo_bundle.json" \
  --output-root "data/sprout/demo_project" \
  --shot-ids shot_001
```

如需显式指定视频模型：

```bash
python3 -m agents.sprout generate-shots \
  --bundle-file "data/sprout/demo_project/script/sprout_demo_bundle.json" \
  --output-root "data/sprout/demo_project" \
  --shot-ids shot_001 \
  --multi-reference-video-model "你的多参考图模型或接入点" \
  --fallback-multi-reference-video-models "候选模型1,候选模型2" \
  --single-reference-video-model "你的单图图生模型或接入点"
```

导出执行卡与项目清单：

```bash
python3 -m agents.sprout export \
  --bundle-file "data/sprout/demo_project/script/sprout_demo_bundle.json" \
  --output-root "data/sprout/demo_project"
```

### 离线自检

当前已补充不触网的冒烟测试：

```bash
python3 -m unittest agents.sprout.tests.test_sprout_smoke
```

## 当前已验证的真实问题

### 1. `plan-topic` 初版会遇到 LLM 超时

- 已在 `script_planner` 中提高默认超时时间并增加重试

### 2. 多参考图视频依赖 `Seedance 2.0` 系列模型权限

- 当前账号环境下，`doubao-seedance-2-0-fast` 与 `doubao-seedance-2-0` 都返回无权限或不存在
- 因此 `generate-shots` 已增加降级路径：
  - 先用多图生成关键帧
  - 再回退到单图 `i2v` 生成视频
- 如果你的账号后续开通了 `Seedance 2.0`，可直接通过 CLI 参数覆盖模型名进行测试
