# AccretionDisk

面向 AIGC 智能体研发的项目仓库，当前重点沉淀文本、图像、视频及多模态相关的基础能力、工程模块、工作文档与可复用技能。

## 项目定位

`AccretionDisk` 主要用于：

- 构建和迭代不同类型的智能体
- 沉淀可复用的基础模块与调用封装
- 记录项目过程文档、知识经验与技能模板

## 目录结构

```text
AccretionDisk/
├── AGENTS.md           # 项目协作准则与目录约定
├── LICENSE             # 许可证
├── agents/             # 不同智能体实现
├── config/             # 配置文件
├── data/               # 按智能体划分的数据目录
├── doc/                # 项目工作记录与阶段文档
├── module/             # 可复用基础模块
├── script/             # 常用脚本
├── skills/             # 项目内可复用 Skill
├── tmp/                # 临时文件与测试产物
└── wiki/               # 可跨任务复用的知识沉淀
```

## 目录说明

| 目录 | 说明 |
| --- | --- |
| `agents/` | 存放不同智能体代码，通常按 `agents/{agent_name}` 组织 |
| `config/` | 存放项目配置，区分私密配置与可提交公共参数配置 |
| `data/` | 存放项目数据，通常按智能体或任务拆分 |
| `doc/` | 面向项目管理与工作推进的记录文档，按 `doc/YYYYMMDD/` 归档 |
| `module/` | 面向开发复用的基础模块代码 |
| `script/` | 存放任务启动、处理、辅助脚本 |
| `skills/` | 项目级 Skill，沉淀特定工作流与调用规范 |
| `tmp/` | 临时文件、测试结果、运行产物，通常不纳入版本控制 |
| `wiki/` | 面向长期复用的知识总结与经验抽象 |

## 当前模块重点

目前已接入的基础能力主要位于以下两个方向：

- `module/api/seed/`
- `module/database/Supabase/`

其中 `module/api/seed/` 主要包括：

- 文本与多模态理解接口
- 生图接口
- 视频生成任务接口
- 配置加载与本地下载能力

`module/database/Supabase/` 当前主要包括：

- Supabase 配置读取
- `anon` / `service_role` 客户端初始化
- `Auth / Session / User` 基础封装
- 项目级最小角色模型
- 项目域表访问与 Storage 路径工具
- `sprout` 二期数据库结构与 RLS 参考 SQL

相关说明可查看：

- `module/api/seed/readme.md`
- `module/database/Supabase/readme.md`
- `doc/20260405/seed-api-issue-note.md`
- `doc/20260408/supabase-python-auth-module.md`
- `doc/20260408/supabase-sprout-phase2-design.md`
- `wiki/seed/`
- `wiki/supabase/`
- `wiki/sprout/`

## 协作约定

项目协作与目录使用规则以 `AGENTS.md` 为准，重点包括：

- 工作语言使用中文
- 不同类型信息分别沉淀到 `readme`、`doc`、`wiki`
- 临时测试数据优先放到 `tmp/`
- 模块代码尽量保持可复用、可扩展

## 建议阅读顺序

如果是首次进入项目，建议按下面顺序阅读：

1. `AGENTS.md`
2. `README.md`
3. `module/api/seed/readme.md`
4. `module/database/Supabase/readme.md`
5. `doc/` 与 `wiki/` 中对应主题内容
