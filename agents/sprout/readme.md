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
- 工作台后端项目导入、版本记录与 API 服务
- 面向创意从业者的原生 `HTML/CSS/JS` 工作台页面（支持用户输入起始节点、工作流管线可视化与一键启动）

## 当前架构分层

`sprout` 当前按下面的目录职责推进：

- `core/`：核心工作流、领域模型、核心存储与编排入口
- `service/`：后端支撑代码，包括项目导入、项目注册表、运行时日志、版本快照、媒体访问和 HTTP API
- `web/`：前端交互代码目录，包含页面、状态、组件、前端 API 封装与样式
- `contracts/`：接口与节点类型共享契约
- 包入口与 CLI：`__init__.py`、`__main__.py`、`run.py` 负责导出与启动；业务实现不再放在顶层

当前已进一步收敛为：

- 真实业务实现只保留在 `core/`
- 顶层历史业务模块已删除
- 后续所有核心流程开发都应直接进入 `core/`

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
- `core/`：核心工作流、模型、共享工具、核心存储
- `service/`：工作台后端 API、项目导入、版本与运行时支持
- `web/`：工作台前端 `HTML/CSS/JS` 代码
- `contracts/`：共享接口契约与节点类型常量
- `run.py` / `__main__.py`：命令行与服务启动入口
- `web_plan.md`：工作台两期计划

当前真实实现只放在这些路径：

- `core/schema.py`
- `core/utils.py`
- `core/script_planner.py`
- `core/character_builder.py`
- `core/shot_pipeline.py`
- `core/jimeng_packager.py`
- `core/exporter.py`
- `core/project_store.py`
- `core/workflow.py`

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

### 一期后端命令

导入已有项目目录：

```bash
python3 -m agents.sprout import-project \
  --project-root "data/sprout/node_test_case" \
  --import-mode reference
```

查看已导入项目：

```bash
python3 -m agents.sprout list-projects
```

启动一期后端 API：

```bash
python3 -m agents.sprout serve-api \
  --host 127.0.0.1 \
  --port 8765
```

启动后，浏览器直接打开：

- `http://127.0.0.1:8765/`

当前工作台已支持：

- 通过原生目录选择器选择项目目录
- 选择已有项目时忠实导入，选择空目录时初始化为空项目
- 查看项目列表与摘要
- **用户输入起始节点**：记录题材/时长/镜头数/分镜文本，并纳入版本管理
- **脚本分镜节点**：与角色资产并行展示剧情、脚本、分镜与分镜图片预览
- **可视化工作流管线**：直观展示项目节点进度与状态
- **节点详情查看**：根据节点类型（剧本、角色、镜头等）定制化的美观卡片展示
- **一键启动工作流**：前端自动编排，依次执行未完成的节点
- **节点双模交互**：工作流节点支持直接点击（同页无刷新切换）和按住 Cmd/Ctrl 点击（新标签页打开）
- 版本切换与版本内容查看
- 节点重跑
- 日志查看
- 图片与视频产物预览

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
python3 -m unittest \
  agents.sprout.tests.test_sprout_smoke \
  agents.sprout.tests.test_sprout_backend_phase1
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
