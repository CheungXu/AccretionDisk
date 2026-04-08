---
name: supabase
description: 使用项目内 `module/database/Supabase/` 模块完成 Supabase 配置读取、客户端初始化、认证调用、项目域表访问、Storage 路径管理与 `sprout` 云端数据访问（`cloud_*` Store 为运行时唯一数据路径）。适用于用户要求调用、扩展、排查、测试或调整 Supabase Python 模块，以及需要检查 `config/supabase_key.json`、`config/supabase_config.json`、注册登录链路、项目表、RLS、Storage 或 admin 用户接口时。
---

# Supabase

## 适用范围

当任务涉及以下内容时，优先使用本 Skill：

- 调用 `create_auth_service()`
- 调用 `create_admin_auth_service()`
- 调用 `create_anon_client()`
- 调用 `create_service_client()`
- 调整 `config/supabase_config.json`
- 检查 `config/supabase_key.json` 与 `SUPABASE_*` 环境变量
- 排查注册、登录、登出、刷新 session、当前用户查询
- 排查管理侧 `list_users()`、`get_user()`
- 排查 `projects / project_members / project_versions / project_runs / project_assets / project_snapshots`
- 排查 Storage 路径、signed URL、对象上传下载
- 扩展 `module/database/Supabase/` 下的配置层、客户端层、认证层、权限层、表访问层或 Storage 层
- 扩展 `agents/sprout/service/cloud_*`（运行时唯一数据路径）

## 代码位置

- 模块目录：`module/database/Supabase/`
- 开发说明：`module/database/Supabase/readme.md`
- 公共配置：`config/supabase_config.json`
- 私密配置：`config/supabase_key.json`
- `sprout` 云端数据层（无历史本地适配层文件；运行时仅经以下四个 Store）：`agents/sprout/service/cloud_project_store.py`、`cloud_asset_store.py`、`cloud_version_store.py`、`cloud_run_store.py`

## 调用原则

1. 默认优先使用项目内封装，不直接跳过模块手写裸请求，除非是在排查协议问题。

2. 配置职责固定：

- `config/supabase_key.json`：不可提交，存放 `url`、`anon_key`、`service_role_key`
- `config/supabase_config.json`：可提交，存放 `schema`、`timeout_seconds`、`headers`、`auth`、`storage`、`sprout` 默认值

3. 配置读取顺序固定：

- 先读环境变量 `SUPABASE_URL`、`SUPABASE_ANON_KEY`、`SUPABASE_SERVICE_ROLE_KEY`
- 若环境变量未提供，再读 `config/supabase_key.json`

4. 调用时如果显式传参，显式参数优先于配置文件默认值。

5. 不要把 `service_role_key` 暴露到前端、不可信环境或提交到仓库。

## 能力映射

### 普通用户侧

优先使用：

- `create_auth_service()`
- `SupabaseAuthService`

常用方法：

- `sign_up()`
- `sign_in_with_password()`
- `sign_out()`
- `refresh_session()`
- `get_current_user()`
- `get_current_session()`

适用场景：

- 邮箱密码注册
- 邮箱密码登录
- 基础 session 管理
- 当前用户校验

### 管理侧

优先使用：

- `create_admin_auth_service()`
- `SupabaseAdminAuthService`

常用方法：

- `list_users()`
- `get_user()`

适用场景：

- 服务端查询用户列表
- 服务端按用户 ID 查询账号

注意：

- 管理侧接口需要 `service_role_key`
- 当前项目封装已经为 admin 请求补了显式 `Bearer service_role_key`
- 如果绕过现有封装手写请求，要记得同时带 `apikey` 和 `Authorization: Bearer <service_role_key>`

### 客户端层

当任务只涉及底层请求或后续扩展时，优先使用：

- `SupabaseClientFactory`
- `SupabaseRestClient`
- `create_anon_client()`
- `create_service_client()`

默认能力：

- 认证接口走 `auth/v1`
- REST 表接口走 `rest/v1`
- Storage 接口走 `storage/v1`
- `schema`、`timeout_seconds`、默认 headers 可从 `config/supabase_config.json` 注入

### 项目域表与权限层

当任务涉及项目协作与数据隔离时，优先使用：

- `authorization.py`
- `project_tables.py`

当前最小角色模型：

- `owner`
- `editor`
- `viewer`

当前动作语义：

- `project.read`
- `project.update`
- `project.delete`
- `member.manage`
- `version.activate`
- `run.retry`
- `asset.upload`
- `asset.delete`

当前核心表：

- `profiles`
- `projects`
- `project_members`
- `project_assets`
- `project_snapshots`
- `project_versions`
- `project_runs`

### Storage 层

当任务涉及文件路径、对象上传下载或签名 URL 时，优先使用：

- `storage.py`
- `SupabaseStorageService`

当前路径约定：

- `projects/{project_id}/assets/...`
- `projects/{project_id}/snapshots/...`
- `projects/{project_id}/logs/...`
- `projects/{project_id}/exports/...`

当前已支持 **TUS 分片上传** 协议：`upload_file()`、`upload_bytes()` 对超过 **20MB** 的内容自动分片上传，无需调用方单独分支。

### `sprout` 云端 Store 层

上述四个 `cloud_*` 模块是 **sprout 运行时唯一的数据读写路径**（项目、快照、bundle、版本、运行、资产等均经 Supabase 表 + Storage），不再作为「仅导入期使用的映射辅助层」。涉及项目域数据时优先使用：

- `agents/sprout/service/cloud_project_store.py`
- `agents/sprout/service/cloud_asset_store.py`
- `agents/sprout/service/cloud_version_store.py`
- `agents/sprout/service/cloud_run_store.py`

领域对象与表/存储的对应关系：

- `SproutImportedProjectRecord` -> `projects`
- `SproutProjectBundle` -> `projects` + `project_snapshots`
- `SproutNodeVersionRecord` -> `project_versions`
- `SproutRunRecord` -> `project_runs`
- `SproutAsset` -> `project_assets`

## 当前模块边界

当前 `module/database/Supabase/` 已覆盖：

- 配置读取
- HTTP 客户端初始化
- `Auth / Session / User`
- 项目级最小角色模型
- 项目域表访问
- Storage 路径与对象操作
- `sprout` 二期数据库与 RLS 参考 SQL（`sprout` 数据经 `cloud_*` Store 与表 + Storage 交互）

当前不覆盖：

- Realtime
- Edge Functions

如果用户要求做完整 RBAC、Realtime 或 Edge Functions，可以复用当前模块作为底座，但不要误判为这些能力已经全部内建完成。

## 工作流程

### 调用或联调 Supabase 时

1. 先检查 `config/supabase_key.json` 是否已填写真实值。
2. 再检查 `config/supabase_config.json` 中的默认参数是否符合当前 Workspace。
3. 优先跑最小真实链路：

- `sign_up()`
- `sign_in_with_password()`
- `get_current_user()`
- `sign_out()`

4. 如果是服务端管理链路，再补：

- `list_users()`
- `get_user()`

5. 如果是二期项目协作链路，再补：

- `projects`
- `project_members`
- `project_versions`
- `project_runs`
- `project_assets`
- `project_snapshots`
- `sprout_phase2_schema.sql`
- `sprout_phase2_rls.sql`

6. 改动完成后，至少做一轮真实或最小可验证测试。
7. 如有重要结论，同步更新 `readme`、`doc`、`wiki`。

### 扩展 Supabase 模块时

1. 先看 `module/database/Supabase/readme.md`
2. 优先复用现有结构与命名
3. 配置相关改动优先落到 `config.py`
4. HTTP 请求相关改动优先落到 `client.py`
5. 认证流程相关改动优先落到 `auth.py`
6. 涉及配置模板或安全约定时，同步检查 `.gitignore`

### 排查问题时

1. 先判断是配置错误、认证策略问题，还是本地封装问题。
2. 优先保留：

- 请求路径
- HTTP 状态码
- Supabase 原始错误消息

3. 常见排查顺序：

- `url` 是否正确
- `anon_key` / `service_role_key` 是否真实可用
- 注册是否返回 `user`
- 登录是否返回 `access_token`
- `get_current_user()` 是否能拿到当前用户
- admin 接口是否正确带上 Bearer token
- 项目表是否都带 `project_id`
- `project_members` 是否作为统一授权中心
- Storage 路径是否遵守 `projects/{project_id}/...`
- 数据表 RLS 与 Storage policy 是否一致

## 安全约定

- `config/supabase_key.json` 只用于本地私密配置
- `config/supabase_key.json` 必须加入版本控制忽略
- 不要在代码、日志、文档中明文回显完整密钥
- 给用户回报联调结果时，只报告“是否已配置”或“是否成功”，不要回显敏感值

## 附加资料

- 使用示例见 [examples.md](examples.md)
- 开发说明见 [../../../module/database/Supabase/readme.md](../../../module/database/Supabase/readme.md)
