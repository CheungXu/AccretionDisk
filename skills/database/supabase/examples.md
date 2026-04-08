# Supabase Skill 示例

## 检查配置是否已填写

```python
from module.database.Supabase.config import load_supabase_secret

secret = load_supabase_secret()
print({
    "url_configured": bool(secret.url),
    "anon_key_configured": bool(secret.anon_key),
    "service_role_key_configured": bool(secret.service_role_key),
})
```

## 普通用户登录并查询当前用户

```python
from module.database.Supabase import create_auth_service

auth_service = create_auth_service()
login_result = auth_service.sign_in_with_password(
    email="demo@example.com",
    password="your-password",
)
print(bool(login_result.get("access_token")))

current_user = auth_service.get_current_user()
print(current_user.get("email"))
```

## 注册后登出

```python
from module.database.Supabase import create_auth_service

auth_service = create_auth_service()
auth_service.sign_up(
    email="demo@example.com",
    password="your-password",
)
auth_service.sign_out()
```

## 管理侧查询用户列表

```python
from module.database.Supabase import create_admin_auth_service

admin_service = create_admin_auth_service()
users_result = admin_service.list_users(page=1, per_page=20)
print(len(users_result.get("users", [])))
```

## 管理侧查询单个用户

```python
from module.database.Supabase import create_admin_auth_service

admin_service = create_admin_auth_service()
user_result = admin_service.get_user("your-user-id")
print(user_result.get("user", {}).get("email"))
```

## 调整默认公共配置

优先修改：

- `config/supabase_config.json`

常见配置项：

- `schema`
- `timeout_seconds`
- `headers.X-Client-Info`
- `auth.persist_session`
- `auth.auto_refresh_token`
- `auth.default_email_redirect_to`
- `storage.bucket_name`
- `storage.path_prefix`
- `storage.signed_url_ttl_seconds`
- `sprout.default_project_type`

## 最小角色模型判断

```python
from module.database.Supabase import (
    PROJECT_ACTION_UPDATE,
    PROJECT_ROLE_EDITOR,
    role_has_action,
)

print(role_has_action(PROJECT_ROLE_EDITOR, PROJECT_ACTION_UPDATE))
```

## 查询项目表

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
print(projects)
```

## 构造 Storage 路径

```python
from module.database.Supabase import create_storage_service

storage = create_storage_service()
asset_path = storage.build_asset_object_path(
    project_id="sprout_demo",
    asset_type="shot_video",
    asset_id="shot_001_video_01",
    file_name="shot_001_01.mp4",
)
print(asset_path)
```

## 从云端下载项目 bundle 快照

```python
from agents.sprout.service.cloud_project_store import SproutCloudProjectStore

store = SproutCloudProjectStore()
bundle_data = store.download_latest_bundle_snapshot("sprout_demo")
print(bundle_data.get("project_name"))
```

## 构造版本记录行

```python
from agents.sprout.service.cloud_version_store import SproutCloudVersionStore
from agents.sprout.service.types import SproutNodeVersionRecord

version_record = SproutNodeVersionRecord(
    version_id="version_prepare_shot_shot_001_202604080001",
    project_id="sprout_demo",
    node_type="prepare_shot",
    node_key="shot_001",
    bundle_snapshot_path="projects/sprout_demo/snapshots/node_version/version_prepare_shot_shot_001.json",
)

store = SproutCloudVersionStore()
row = store.build_version_row(version_record, snapshot_id="snapshot_001")
print(row["snapshot_id"])
```
