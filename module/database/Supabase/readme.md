# Supabase 模块说明

## 模块定位

`module/database/Supabase/` 用于沉淀可跨项目复用的 Supabase Python 基础能力。

当前已经分为两层：

- 配置读取
- 客户端初始化
- `Auth / Session / User` 基础封装
- 项目级最小角色模型
- 项目域表访问层
- Storage 路径与对象操作封装
- `sprout` 二期数据库与 RLS 参考 SQL

当前仍暂不包含：

- 完整 RBAC 权限表
- Realtime
- Edge Functions
- 直接耦合 `sprout` 全部业务逻辑的工作流编排

## 目录结构

```text
module/database/Supabase/
├── __init__.py
├── authorization.py
├── auth.py
├── client.py
├── config.py
├── plan.md
├── project_tables.py
├── readme.md
├── sprout_phase2_rls.sql
├── sprout_phase2_schema.sql
└── storage.py
```

## 配置文件

### 私密配置

文件：

- `config/supabase_key.json`

职责：

- 保存 `url`
- 保存 `anon_key`
- 保存 `service_role_key`

该文件默认不会提交到仓库。

模板示例：

```json
{
  "url": "请填写 Supabase 项目 URL",
  "anon_key": "请填写匿名访问密钥",
  "service_role_key": "请填写服务端管理密钥"
}
```

同时支持环境变量兜底：

- `SUPABASE_URL`
- `SUPABASE_ANON_KEY`
- `SUPABASE_SERVICE_ROLE_KEY`

### 公共配置

文件：

- `config/supabase_config.json`

职责：

- 保存非敏感默认参数
- 统一控制模块默认行为
- 保存 Storage 与 `sprout` 二期默认参数

模板示例：

```json
{
  "project_name": "请填写项目标识",
  "schema": "public",
  "timeout_seconds": 30,
  "headers": {
    "X-Client-Info": "AccretionDisk-Supabase/1.0"
  },
  "auth": {
    "persist_session": true,
    "auto_refresh_token": true,
    "default_email_redirect_to": ""
  },
  "storage": {
    "bucket_name": "sprout-projects",
    "path_prefix": "projects",
    "signed_url_ttl_seconds": 3600,
    "public_bucket": false
  },
  "sprout": {
    "default_project_type": "sprout",
    "default_member_role": "owner",
    "phase2_enabled": true
  }
}
```

## 能力说明

### `config.py`

提供：

- `load_supabase_secret()`
- `load_supabase_config()`
- `load_supabase_section()`
- `load_supabase_storage_config()`
- `load_json_file()`

### `client.py`

提供：

- `SupabaseRestClient`
- `SupabaseClientFactory`
- `create_anon_client()`
- `create_service_client()`

当前基于标准库 `urllib` 实现，不额外引入第三方依赖，并已支持：

- `auth/v1`
- `rest/v1`
- `storage/v1`

### `auth.py`

普通用户侧能力：

- `sign_up()`
- `sign_in_with_password()`
- `sign_out()`
- `refresh_session()`
- `get_current_user()`

管理侧能力：

- `list_users()`
- `get_user()`
- `create_user()`
- `find_user_by_email()`
- `update_user_by_id()`

### `authorization.py`

提供项目级最小角色模型：

- `owner`
- `editor`
- `viewer`

并统一收口动作语义：

- `project.read`
- `project.update`
- `project.delete`
- `member.manage`
- `version.activate`
- `run.retry`
- `asset.upload`
- `asset.delete`

### `project_tables.py`

提供项目域表常量与 PostgREST 访问封装：

- `profiles`
- `projects`
- `project_members`
- `project_assets`
- `project_snapshots`
- `project_versions`
- `project_runs`

常用入口：

- `SupabaseProjectTableService`
- `SupabaseTableFilter`
- `create_project_table_service()`

### `storage.py`

提供 Storage 路径规则和对象操作：

- `SupabaseStorageService`
- `create_storage_service()`
- `build_asset_object_path()`
- `build_snapshot_object_path()`
- `build_log_object_path()`
- `upload_file()`
- `upload_bytes()`
- `upload_text()`
- `download_object()`
- `create_signed_url()`

`upload_file()` 和 `upload_bytes()` 对超过 20MB 的文件自动走 TUS 分片上传协议。

### `sprout_phase2_schema.sql`

提供 `sprout` 二期的数据库结构参考，包括：

- `profiles`
- `projects`（含 `active_state` JSONB 列，用于存放版本激活状态等）
- `project_members`
- `project_assets`
- `project_snapshots`
- `project_versions`
- `project_runs`
- `sprout-projects` bucket 初始化

### `sprout_phase2_rls.sql`

提供 `sprout` 二期的 RLS 与 Storage policy 参考，包括：

- `project_members` 作为统一授权中心
- 项目域表的 `select / insert / update / delete` policy
- Storage `projects/{project_id}/...` 前缀策略

## 最小使用示例

普通认证：

```python
from module.database.Supabase import create_auth_service

auth_service = create_auth_service()
login_result = auth_service.sign_in_with_password(
    email="demo@example.com",
    password="your-password",
)
current_user = auth_service.get_current_user()
```

管理侧查询：

```python
from module.database.Supabase import create_admin_auth_service

admin_service = create_admin_auth_service()
users = admin_service.list_users(page=1, per_page=20)
```

项目域表：

```python
from module.database.Supabase import (
    SupabaseTableFilter,
    TABLE_PROJECTS,
    create_project_table_service,
)

table_service = create_project_table_service()
projects = table_service.select_rows(
    TABLE_PROJECTS,
    filters=[SupabaseTableFilter("project_id", "eq", "sprout_demo")],
)
```

Storage 路径：

```python
from module.database.Supabase import create_storage_service

storage = create_storage_service()
object_path = storage.build_snapshot_object_path(
    project_id="sprout_demo",
    snapshot_type="bundle",
    file_name="bundle.json",
)
```

## 安全说明

- `anon_key` 仅用于普通访问上下文
- `service_role_key` 仅用于服务端管理任务
- 不要把 `service_role_key` 暴露到前端或不可信环境
- `config/supabase_key.json` 应保持本地私有，不提交仓库
- 管理侧用户接口与 Storage 管理操作优先走服务端客户端
- `sprout` 二期 RLS 默认围绕 `project_members` 做项目隔离

## 后续扩展建议

当前已经具备二期底座，以下两项已完成：

- `sprout` API 与工作台接入云端项目存储
- Storage 上传联调与签名 URL 下发

后续若继续扩展，可优先考虑：

- 完整 RBAC 表：`roles / permissions / role_permissions`
- Realtime / RPC / Edge Functions
