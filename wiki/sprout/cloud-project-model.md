# Sprout 云端项目模型

## 当前状态

该模型已于 2026-04-08 完成全面落地。所有运行时数据已迁移至 Supabase 数据库与 Storage，服务层不再依赖本地文件系统。

## 目的

`sprout` 现在同时存在：

- 项目注册信息
- 项目整包
- 节点版本快照
- 运行记录
- 图片与视频产物

如果这些信息继续完全留在本地磁盘中，后续多人协作和跨环境访问会越来越难。

因此需要把 `sprout` 的核心对象映射到云端项目模型。

## 对象映射

当前推荐映射关系如下：

### 项目

本地对象：

- `SproutImportedProjectRecord`
- `SproutProjectBundle`

云端表：

- `projects`
- `project_snapshots`

说明：

- `projects` 保存项目主信息；表内新增 `active_state` JSONB 列，存放版本激活状态
- `project_snapshots` 保存 bundle / manifest / 导出快照的文件元数据

### 成员

云端表：

- `project_members`

说明：

- 这是项目隔离和权限判断的核心表
- 当前先按 `owner / editor / viewer` 三档角色管理

### 资产

本地对象：

- `SproutAsset`

云端表：

- `project_assets`

Storage：

- `projects/{project_id}/assets/...`

说明：

- 表里只保留元数据和对象路径
- 图片、视频等真实文件进入 Storage

### 版本

本地对象：

- `SproutNodeVersionRecord`

云端表：

- `project_versions`
- `project_snapshots`

说明：

- 版本记录表保存结构化信息
- 版本快照文件保存到 Storage

### 运行记录

本地对象：

- `SproutRunRecord`

云端表：

- `project_runs`

Storage：

- `projects/{project_id}/logs/...`

说明：

- 日志文本不直接塞进主表
- 主表保存日志对象路径和状态

## 为什么项目是最核心的隔离单元

对于 `sprout`，项目天然就是最清晰的权限边界：

- 一个短剧项目的角色、镜头、版本、产物通常只属于该项目
- 协作者通常也是按项目加入，而不是按单个资产加入

因此二期应统一围绕 `project_id` 展开：

- 数据表带 `project_id`
- Storage 路径带 `project_id`
- RLS 围绕 `project_members.project_id`

## Storage 路径建议

当前建议：

- `projects/{project_id}/assets/...`
- `projects/{project_id}/snapshots/...`
- `projects/{project_id}/logs/...`
- `projects/{project_id}/exports/...`

这样后续无论是：

- 签名 URL
- 对象清理
- 生命周期策略
- RLS / Storage policy

都会更容易保持一致。

## 实施建议

已按两层实施：

### 1. 通用层

放在：

- `module/database/Supabase/`

负责：

- 配置
- 表访问
- 角色判断
- Storage 路径

### 2. 项目映射层

放在：

- `agents/sprout/service/cloud_*`

负责：

- 把 `sprout` 本地对象映射成数据库行
- 把本地资产和快照映射成 Storage 对象

这样就能做到：

- Supabase 模块保持通用
- `sprout` 业务规则仍然留在 `sprout` 自己的服务层
