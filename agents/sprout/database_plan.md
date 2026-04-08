# Sprout 数据库二期计划

## 背景

当前 `sprout` 已经具备本地项目注册、节点版本快照、运行日志、媒体访问和工作台能力，但数据主要仍落在本地目录与 JSON 文件中。

现有云端基础已完成第一阶段：

- `module/database/Supabase/` 已支持配置读取
- 已支持 `anon` / `service_role` 客户端初始化
- 已支持注册、登录、登出、刷新 session、当前用户查询
- 已支持管理侧用户查询

第二阶段的目标，是在不破坏第一阶段认证底座的前提下，把 `sprout` 的项目协作、版本记录、运行记录、资产元数据和文件存储统一迁移到 Supabase 方案中。

## 当前业务对象对齐

结合现有代码和数据样例，当前 `sprout` 的核心云端对象已经比较明确：

- 项目：`SproutProjectBundle`
- 资产：`SproutAsset`
- 角色：`SproutCharacter`
- 镜头：`SproutShot`
- 工作流卡：`SproutWorkflowCard`
- 项目清单：`SproutManifest`
- 项目注册记录：`SproutImportedProjectRecord`
- 节点版本记录：`SproutNodeVersionRecord`
- 节点运行记录：`SproutRunRecord`

这些对象分别来自：

- `agents/sprout/core/schema.py`
- `agents/sprout/service/types.py`
- `data/sprout/project_registry/projects.json`

## 设计目标

第二阶段希望同时解决以下问题：

1. 用户登录后，只能看到自己参与的项目。
2. 项目成员能够按角色协作，而不是所有登录用户都拥有同等权限。
3. 项目版本、运行记录和资产元数据进入结构化数据库，便于查询和管理。
4. 图片、视频、快照、日志等文件进入 Storage，而不是继续完全依赖本地磁盘。
5. 方案要兼顾当前快速落地和后续升级到 RBAC。

## 前置事项

在正式进入数据库二期开发前，先把当前历史提交推送到远程，作为后续云端改造的稳定基线。

这样做的目的：

- 先固化当前一期后端、工作台和第一阶段 Supabase 底座的历史状态
- 避免数据库二期与之前本地改动混在一起，导致后续回溯困难
- 让后续 Supabase 二期改造能够基于明确的远程版本继续推进

执行时建议先确认：

- 当前分支和目标远程分支
- 本地是否还有不希望一起推送的未提交改动
- 推送后是否再从该远程基线继续开展数据库二期开发

## 权限模型选择

本阶段采用：

- 项目级最小角色模型
- 角色为 `owner / editor / viewer`
- 但在命名和服务层抽象上预留升级到 RBAC 的路径

### 当前角色语义

`owner`

- 创建和删除项目
- 管理项目成员
- 激活或切换版本
- 查看和修改全部项目数据
- 触发运行、重跑节点、上传和删除资产

`editor`

- 查看项目
- 修改项目内容
- 触发运行与生成版本
- 上传资产
- 查看日志、快照和产物

`viewer`

- 只读查看项目、版本、运行记录、日志和产物
- 不允许修改项目内容
- 不允许重跑节点
- 不允许管理成员

### 为什么先不用完整 RBAC

当前 `sprout` 最核心的资源边界是项目，而不是复杂后台权限点。

如果现在直接上完整 RBAC：

- 表会更多
- RLS 会更复杂
- `module` 和 `skills` 的扩展范围也会明显变重

对于当前目标，更适合先把项目协作和数据隔离跑通。

### 如何预留 RBAC 升级路径

虽然本阶段不建 `roles / permissions / role_permissions` 表，但会提前约定动作语义：

- `project.read`
- `project.update`
- `project.delete`
- `member.manage`
- `version.activate`
- `run.retry`
- `asset.upload`
- `asset.delete`

当前代码和文档里的权限判断，尽量围绕这些动作语义组织，而不是把判断散落在业务代码各处。这样后面升级到 RBAC 时，只需要替换权限来源，不需要整体推翻设计。

## ID 与映射策略

为了减少从现有本地数据迁移到云端的成本，本阶段优先保留现有字符串 ID 体系，而不是强制改成全新的 UUID 主键。

建议：

- `profiles.id` 继续使用 Supabase `auth.users.id` 的 UUID
- `projects.project_id` 继续沿用当前 `sprout` 的字符串项目 ID
- `project_versions.version_id` 继续沿用当前版本 ID
- `project_runs.run_id` 继续沿用当前运行 ID
- `project_assets.asset_id` 继续沿用当前资产 ID

这样能够直接兼容：

- `data/sprout/project_registry/projects.json`
- `SproutNodeVersionRecord`
- `SproutRunRecord`
- `SproutAsset`

后续如果确实需要再增加内部代理主键，可以作为补充字段，而不是当前阶段就强制改动。

## 数据库存储范围

本阶段采用：

- 结构化数据进数据库
- 文件进 Storage
- 数据库只保存文件元数据和引用

### 进入数据库的内容

- 项目基础信息
- 项目成员关系
- 版本记录
- 运行记录
- 资产元数据
- 快照元数据
- 用户资料

### 进入 Storage 的内容

- 图片资产
- 视频资产
- bundle JSON
- manifest JSON
- 节点版本快照 JSON
- 运行日志文件
- 未来导出包或中间产物

## 核心表设计

### `profiles`

作用：

- 作为 `auth.users` 的补充资料表
- 保存业务侧展示信息

建议字段：

- `id`
- `display_name`
- `avatar_url`
- `email`
- `created_at`
- `updated_at`

### `projects`

作用：

- 替代当前本地 `project_registry` 中的主项目记录

建议字段：

- `project_id`
- `project_type`
- `display_name`
- `project_name`
- `title`
- `topic`
- `status`
- `schema_version`
- `import_mode`
- `health_status`
- `cover_asset_id`
- `current_manifest_snapshot_id`
- `created_by`
- `imported_at`
- `last_active_at`
- `metadata`

其中：

- `project_id` 直接兼容当前本地项目 ID
- `metadata` 可承接当前项目注册表中暂时不适合拆列的附加信息

### `project_members`

作用：

- 承载项目级最小角色模型
- 作为 RLS 的授权中心

建议字段：

- `project_id`
- `user_id`
- `role`
- `invited_by`
- `joined_at`
- `updated_at`
- `status`

约束建议：

- `(project_id, user_id)` 唯一
- `role` 限制为 `owner / editor / viewer`

### `project_assets`

作用：

- 承接 `SproutAsset`
- 保存 Storage 对象引用，而不是把大文件塞进表里

建议字段：

- `asset_id`
- `project_id`
- `asset_type`
- `source`
- `bucket_name`
- `object_path`
- `public_url`
- `role`
- `prompt`
- `owner_user_id`
- `shot_id`
- `character_id`
- `metadata`
- `created_at`

说明：

- 当前 `SproutAsset.owner_id` 建议在云端解释为 `owner_user_id`
- `shot_id`、`character_id` 用于将资产挂到镜头或角色维度

### `project_versions`

作用：

- 承接 `SproutNodeVersionRecord`

建议字段：

- `version_id`
- `project_id`
- `node_type`
- `node_key`
- `snapshot_id`
- `source_version_id`
- `status`
- `run_id`
- `asset_ids`
- `shot_ids`
- `dependency_version_ids`
- `notes`
- `created_at`

说明：

- `asset_ids`、`shot_ids`、`dependency_version_ids` 在第一版可先继续保持数组或 `jsonb` 结构
- 当前重点是兼容本地版本记录，而不是过早做过度范式化

### `project_runs`

作用：

- 承接 `SproutRunRecord`

建议字段：

- `run_id`
- `project_id`
- `node_type`
- `node_key`
- `log_bucket_name`
- `log_object_path`
- `status`
- `source_version_id`
- `result_version_id`
- `shot_ids`
- `error_message`
- `created_at`
- `updated_at`

说明：

- 当前 `log_path` 迁移为 Storage 对象路径，不建议把全部日志文本直接塞数据库

### `project_snapshots`

作用：

- 保存 bundle、manifest、节点版本快照等文件元数据

建议字段：

- `snapshot_id`
- `project_id`
- `snapshot_type`
- `bucket_name`
- `object_path`
- `content_sha256`
- `source_version_id`
- `created_by`
- `created_at`
- `metadata`

`snapshot_type` 建议初版支持：

- `bundle`
- `manifest`
- `node_version`
- `export`

## Storage 设计

本阶段优先采用单 bucket + 项目路径前缀的方式，避免一开始维护过多 bucket。

建议 bucket：

- `sprout-projects`

建议对象路径规范：

- `projects/{project_id}/assets/...`
- `projects/{project_id}/snapshots/...`
- `projects/{project_id}/logs/...`
- `projects/{project_id}/exports/...`

### 为什么先用单 bucket

优点：

- 管理简单
- 策略集中
- 项目隔离天然可以通过 `project_id` 前缀表达

如果未来媒体和快照的生命周期策略差异很大，再拆分 bucket 即可。

## RLS 与访问控制设计

RLS 的授权中心统一使用 `project_members`。

### 基础原则

所有项目域表必须带 `project_id`，所有策略围绕“当前用户是否是该项目成员”来判断。

### 读权限

- `viewer / editor / owner` 都可以读项目、版本、运行记录、资产元数据、快照元数据

### 写权限

- `editor / owner` 可写：
  - `projects` 的可编辑字段
  - `project_versions`
  - `project_runs`
  - `project_assets`
  - `project_snapshots`

### 高权限操作

只有 `owner` 可执行：

- 修改成员角色
- 移除成员
- 删除项目
- 激活主版本
- 修改项目级关键配置

### Storage 策略

Storage 的访问策略必须与数据库策略一致：

- 只有项目成员才能访问 `projects/{project_id}/...`
- `viewer` 默认只读
- `editor / owner` 可上传
- 删除类操作优先收敛到 `owner`

## 模块更新规划

第二阶段继续扩展 `module/database/Supabase/`，但不把 `sprout` 的全部业务规则直接塞进认证文件。

### 继续保留

- `config.py`
- `client.py`
- `auth.py`

### 预计新增

- `authorization.py`
- `storage.py`
- `project_tables.py`

### 文件职责建议

`authorization.py`

- 收口 `owner / editor / viewer`
- 提供动作语义到角色的判断函数
- 为后续升级到 RBAC 预留切换点

`storage.py`

- 统一 bucket 名称与对象路径生成
- 统一上传、下载、签名 URL、对象删除逻辑

`project_tables.py`

- 封装项目、成员、版本、运行、资产、快照等表的基础读写能力
- 不直接写 `sprout` 特定对象转换逻辑

### 配置扩展建议

`config/supabase_config.json` 第二阶段建议补充：

- `storage.bucket_name`
- `storage.signed_url_ttl_seconds`
- `storage.path_prefix`
- `sprout.default_project_type`

## `sprout` 服务层更新规划

为了保持模块可复用，`sprout` 特有的对象映射建议放回项目自己的 `service/` 层，而不是写死在通用 `Supabase` 模块里。

建议新增或扩展：

- `agents/sprout/service/cloud_project_store.py`
- `agents/sprout/service/cloud_asset_store.py`
- `agents/sprout/service/cloud_version_store.py`
- `agents/sprout/service/cloud_run_store.py`

### 各文件职责

`cloud_project_store.py`

- `SproutImportedProjectRecord`
- `SproutProjectBundle`
- `project_snapshots`

`cloud_asset_store.py`

- `SproutAsset`
- 角色参考图、镜头产物、封面资产的云端映射

`cloud_version_store.py`

- `SproutNodeVersionRecord`
- 快照与版本绑定

`cloud_run_store.py`

- `SproutRunRecord`
- 运行日志对象路径与状态同步

## Skill 更新规划

当前不拆 skill，继续扩展现有：

- `skills/database/supabase/SKILL.md`
- `skills/database/supabase/examples.md`

### 需要补充的内容

在 `SKILL.md` 中新增：

- 项目表设计触发场景
- 成员与角色设计触发场景
- RLS 排查工作流
- Storage 路径与策略约定
- 版本、运行记录、快照、资产元数据的排查入口

在 `examples.md` 中新增：

- 项目创建示例
- 项目成员查询示例
- 版本记录写入示例
- Storage 路径生成示例
- RLS 调试思路示例

## 文档更新规划

### 需要更新的 readme

至少同步更新：

- `README.md`
- `module/database/Supabase/readme.md`
- `agents/sprout/readme.md`

如果工作台 API 直接接入云端项目能力，再补：

- `agents/sprout/web/readme.md`

### 需要新增的 doc

建议新增：

- `doc/20260408/supabase-sprout-phase2-design.md`

内容包括：

- 为什么选择最小角色模型
- 数据库与 Storage 边界
- 计划新增的模块和服务层
- RLS 设计原则
- 风险和后续事项

### 需要更新或新增的 wiki

建议更新：

- `wiki/supabase/configuration.md`

建议新增：

- `wiki/supabase/permission-model.md`
- `wiki/sprout/cloud-project-model.md`

内容包括：

- 最小角色模型与 RBAC 的关系
- `project_id` 前缀式 Storage 约定
- `sprout` 本地对象到云端表的映射原则
- 后续升级到 RBAC 的演进路径

## 实施顺序

1. 先把当前历史提交推送到远程，固化数据库二期改造前的基线版本。
2. 再扩展 `module/database/Supabase/` 的二阶段底层能力。
3. 明确数据库表设计与 Storage 路径约定。
4. 在 `sprout/service/` 中补云端映射层。
5. 先完成项目、成员、版本、运行、资产元数据的读写路径。
6. 再补 RLS 与 Storage 访问策略。
7. 更新 `skills/database/supabase/` 的二阶段说明和示例。
8. 最后同步更新 `README`、`doc`、`wiki`。

## 验收标准

第二阶段完成后，至少应满足：

- 登录用户只能看到自己参与的项目
- `owner / editor / viewer` 权限差异真实生效
- 项目、成员、版本、运行记录、资产元数据可落到数据库
- 图片、视频、快照、日志能落到 Storage
- 数据表与 Storage 的授权边界保持一致
- `module/database/Supabase/` 仍保持可复用，而不是完全和 `sprout` 强耦合
- `skills`、`readme`、`doc`、`wiki` 同步更新完成

## 风险与后续升级

本阶段最重要的风险不是技术上“做不到”，而是“做得过重”。

需要避免：

- 过早把完整 RBAC 一次做完
- 过早把 `sprout` 所有业务对象直接写死在通用模块里
- 把大文件直接存进数据库
- 让数据库 RLS 和 Storage 权限产生分叉

本阶段结束后，如果协作需求变复杂，再进入下一步：

- 引入 `roles`
- 引入 `permissions`
- 引入 `role_permissions`
- 把当前最小角色模型平滑升级为完整 RBAC
