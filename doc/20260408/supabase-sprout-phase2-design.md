# Sprout Supabase 二期设计记录

> **注意：** 本文档为二期设计阶段的历史记录。云端迁移已全面完成，最终实施记录见 [sprout-cloud-migration-complete.md](./sprout-cloud-migration-complete.md)。

## 工作背景

当前 `sprout` 已经具备本地项目注册、节点版本快照、运行日志、媒体访问和工作台能力，但这些数据主要仍然依赖本地目录和 JSON 文件。

为支持后续多人协作和云端项目隔离，本轮在现有 Supabase 一期认证底座上，开始补二期数据库与 Storage 方案。

## 本次范围

本次工作聚焦：

- 设计并落地 `sprout` 二期数据库结构参考
- 增加项目级最小角色模型
- 增加项目域表访问层
- 增加 Storage 路径与对象操作层
- 增加 `sprout/service` 的云端映射层
- 同步更新 skill、readme、doc、wiki

本次不包含：

- 真实创建远端表
- 真实下发 RLS policy 到线上 Workspace
- 完整 RBAC 表
- 工作台直接切换到云端项目源

## 设计结论

当前采用：

- 最小角色模型：`owner / editor / viewer`
- 后续预留升级到 RBAC 的动作语义
- 结构化数据进数据库
- 图片、视频、快照、日志进 Storage

当前数据库核心表：

- `profiles`
- `projects`
- `project_members`
- `project_assets`
- `project_snapshots`
- `project_versions`
- `project_runs`

当前 Storage 主路径约定：

- `projects/{project_id}/assets/...`
- `projects/{project_id}/snapshots/...`
- `projects/{project_id}/logs/...`
- `projects/{project_id}/exports/...`

## 本次新增代码

`module/database/Supabase/` 新增：

- `authorization.py`
- `storage.py`
- `project_tables.py`
- `sprout_phase2_schema.sql`
- `sprout_phase2_rls.sql`

`agents/sprout/service/` 新增：

- `cloud_project_store.py`
- `cloud_asset_store.py`
- `cloud_version_store.py`
- `cloud_run_store.py`

测试新增：

- `agents/sprout/tests/test_sprout_backend_phase2.py`

## 当前状态

当前已经具备以下二期基础：

- 可在模块层统一判断项目角色能力
- 可在模块层统一生成 Storage 路径
- 可在模块层统一访问项目域表
- 可在 `sprout/service/` 层把项目、资产、版本、运行记录映射为数据库行
- 已补数据库结构与 RLS 参考 SQL

## 风险与约束

当前主要风险：

- 远端 Workspace 还没有实际执行这些表和 policy
- 工作台后端还没有正式切到云端项目源
- 目前仍然是最小角色模型，不是完整 RBAC

需要特别避免：

- 把 `sprout` 全部业务逻辑写死在通用 Supabase 模块里
- 把大 JSON 或媒体文件直接塞进主业务表
- 数据表和 Storage 的权限模型不一致

## 已采取措施

当前已做的控制：

- 通用能力与 `sprout` 映射分层
- 把动作语义集中在 `authorization.py`
- 把对象路径集中在 `storage.py`
- 把表访问集中在 `project_tables.py`
- 用单测覆盖角色能力、路径规则和云端行映射

## 后续事项

- 先确认历史提交推送到远程后的基线
- 再把二期 SQL 真正应用到 Workspace
- 再做真实项目表和 Storage 联调
- 再决定是否把工作台 API 正式接入云端项目存储
- 视协作复杂度决定是否升级到完整 RBAC
