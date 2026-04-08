# Sprout 云数据库完全迁移完成记录

## 工作背景

sprout 此前处于「本地文件系统 + 云端映射层并存」的双轨模式。本次工作将所有运行时数据全面切换到 Supabase 数据库与 Storage，删除全部本地文件系统依赖的历史代码，实现服务层无状态化。

## 本次范围

迁移按 `agents/sprout/cloud_plan.md` 中的阶段全部落地，包括：

- **Phase 0**：远端 Workspace 执行 `sprout_phase2_schema.sql`、`sprout_phase2_rls.sql`，建表与 Storage bucket，并为 `projects` 表补充 `active_state` 列
- **Phase 1**：`active_state` 读写迁入 `projects.active_state`，`cloud_project_store` 提供 `update_active_state` / `get_active_state` / 快照下载能力
- **Phase 2**：`project_service`、`workflow_service` 以云端为主路径，版本/运行/日志经 `cloud_version_store`、`cloud_run_store` 与 Storage，不再依赖本地 `runtime` 目录持久化
- **Phase 3**：`run_node()` 使用临时工作目录，执行结束后将 bundle、资产、版本、日志等上传云端
- **Phase 4**：`media` / `http_api` 经 `project_assets` 与 signed URL（或重定向）访问 Storage，不再直读本地媒体路径
- **Phase 5**：CLI 移除失效的 `import-project`、`list-projects` 等命令
- **Phase 6**：`test_sprout_backend_phase1.py` 等测试改为 FakeTableService / FakeStorageService 覆盖云端主路径
- **Phase 7**：删除本地注册表、本地 runtime、仅导入期使用的云端导入服务等历史代码与本地数据文件

## 数据库变更

- `projects` 表新增 `active_state` jsonb 列
- `sprout_phase2_schema.sql` 同步更新
- `sprout-projects` bucket `file_size_limit` 调整为 500MB

## 服务层改造

主要重写或大幅修改的文件包括：

- `module/database/Supabase/storage.py`（含 TUS 分片上传）
- `module/database/Supabase/sprout_phase2_schema.sql`
- `agents/sprout/service/cloud_project_store.py`
- `agents/sprout/service/cloud_version_store.py`
- `agents/sprout/service/cloud_run_store.py`
- `agents/sprout/service/cloud_asset_store.py`
- `agents/sprout/service/project_service.py`
- `agents/sprout/service/workflow_service.py`
- `agents/sprout/service/media.py`
- `agents/sprout/service/http_api.py`
- `agents/sprout/run.py`（CLI 清理）
- `agents/sprout/service/__init__.py`、`agents/sprout/__init__.py`（导出与云端主路径对齐）
- `agents/sprout/tests/test_sprout_backend_phase1.py`
- `agents/sprout/tests/test_sprout_backend_phase2.py`（按需同步）

## 历史代码删除

以下 **4 个 Python 源文件**已删除（迁移 Phase 7，`cloud_plan.md` 所列模块）：

- `agents/sprout/service/registry.py`（本地 JSON 项目注册表）
- `agents/sprout/service/filesystem_versions.py`（从本地文件推断版本）
- `agents/sprout/service/runtime.py`（本地 runtime 目录读写）
- `agents/sprout/service/cloud_import_service.py`（导入期专用云端导入逻辑，迁移完成后不再需要）

另删除 **1 个本地数据文件**：

- `data/sprout/project_registry/projects.json`

与方案中「5 个源码文件 + 1 个数据文件」的常见表述对齐时：上表为仓库内已不存在的 **4 个独立 `.py` 模块**与 **1 个数据文件**；第 **5 处**通常指 `agents/sprout/run.py` 内移除的 `import-project` / `list-projects` 子命令实现（同文件内整段删除，非独立文件移除），或与「CLI 清理」「包导出收敛」合并计数。

此外，`service/__init__.py`、`agents/sprout/__init__.py` 中已移除对上述已删模块的导出；`cloud_project_store.py`、`project_service.py` 等文件中与 `metadata.local_paths`、本地路径还原相关的逻辑已清理；`types.py` 中部分字段保留兼容用途，见下文「遗留事项」。

## CLI 清理

- 删除 `import-project` / `list-projects` 命令

## 测试重写

- `test_sprout_backend_phase1.py` 完全重写，使用 FakeTableService / FakeStorageService 内存 mock
- 16 个测试全部通过

## Storage 大文件支持

- `storage.py` 新增 TUS 分片上传协议支持
- `upload_file()` 和 `upload_bytes()` 对超过 20MB 的内容自动走 TUS
- 已验证 54.4MB 最终成片上传成功

## 当前状态

- 所有运行时读写通过 Supabase 表 + Storage
- 节点执行使用临时目录，执行完毕后上传结果到云端
- 媒体访问通过 `project_assets` 表查找后从 Storage 下载
- 服务无状态，支持水平扩容
- 全部 16 个单测通过

## 遗留事项

- `SproutImportedProjectRecord` 中的本地路径字段（`project_root`、`canonical_root`、`bundle_path`）仍保留在 `types.py` 中，用于向后兼容云端已有数据的 `metadata.local_paths` 字段，后续可逐步移除
- Storage 全局网关 body size 限制约 50MB，大文件已通过 TUS 分片绕过
