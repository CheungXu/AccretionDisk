# Supabase 配置拆分与认证模块建议

## 适用场景

当项目准备接入 Supabase，且希望把认证、数据库访问、后续权限能力沉淀成可复用模块时，建议先做好配置与职责拆分。

典型场景包括：

- 多个项目复用同一套 Supabase 接入方式
- 账号认证和业务表访问需要逐步演进
- 团队希望避免把敏感密钥散落在代码中

## 推荐做法

建议将 Supabase 配置拆成两类：

### 1. 私密配置

用于不可提交的信息，例如：

- `url`
- `anon_key`
- `service_role_key`

推荐文件：

- `config/supabase_key.json`

这类配置应：

- 默认只保存在本地
- 加入 `.gitignore`
- 支持环境变量兜底

## 2. 公共配置

用于可以共享的默认参数，例如：

- `schema`
- `timeout_seconds`
- 默认请求头
- 认证模块的默认行为
- Storage 默认 bucket 与对象路径前缀
- 项目侧二期默认参数

推荐文件：

- `config/supabase_config.json`

这类配置应：

- 可以提交到仓库
- 作为不同项目共享的默认来源
- 随模块能力扩展逐步补充字段

对 `sprout` 二期，当前建议继续扩展：

- `storage.bucket_name`
- `storage.path_prefix`
- `storage.signed_url_ttl_seconds`
- `storage.public_bucket`
- `sprout.default_project_type`
- `sprout.default_member_role`

## `anon_key` 与 `service_role_key` 的职责区别

### `anon_key`

适合：

- 普通用户上下文
- 浏览器或低权限访问路径
- 依赖 RLS 的受控查询

特点：

- 权限较低
- 更适合作为默认访问上下文

### `service_role_key`

适合：

- 服务端管理任务
- 后台同步任务
- 管理员级接口

特点：

- 权限较高
- 不应暴露到前端
- 不应进入公开环境变量或前端包体

## Python 项目的推荐分层

如果项目使用 Python，建议优先拆成三层：

### 1. 配置层

负责：

- 读取配置文件
- 处理环境变量兜底
- 做基础格式校验

### 2. 客户端层

负责：

- 创建 `anon` 客户端
- 创建 `service` 客户端
- 统一默认超时、请求头、schema

### 3. 业务能力层

第一阶段可只做：

- 注册
- 登录
- 登出
- 刷新 session
- 获取当前用户

后续再扩展：

- 业务表访问
- 角色权限
- RLS 策略
- Storage / Realtime

当前 `sprout` 二期已经把这部分继续往下拆成：

- `authorization.py`
- `project_tables.py`
- `storage.py`
- `agents/sprout/service/cloud_*`

## 为什么先做认证底层

对于大多数项目，认证能力先落地有几个直接收益：

- 可以先把账号链路跑通
- 可以提前验证 Supabase Workspace 是否可用
- 可以避免还没确定业务表就过早绑定数据模型

也就是说，先把“如何接 Supabase”做成模块，再做“项目自身的权限模型”，演进会更平滑。

## 后续扩展建议

当进入第二阶段时，建议重点补：

- `profiles`
- `projects`
- `project_members`
- 角色与权限映射
- RLS 策略

如果业务像 `sprout` 一样同时存在项目、版本、运行记录和资产元数据，建议再进一步拆成：

- `project_assets`
- `project_snapshots`
- `project_versions`
- `project_runs`

如果要给多个项目复用，最好保持：

- 底层客户端与认证模块通用
- 业务模型放在项目侧服务层
- 文档同步沉淀到 `readme`、`doc`、`wiki`

## Storage 配置建议

当项目已经进入二阶段，除了数据库表，Storage 配置也应该统一收口。

对 `sprout`，当前建议：

- bucket：`sprout-projects`
- 路径前缀：`projects/{project_id}/...`

拆分建议：

- 资产：`projects/{project_id}/assets/...`
- 快照：`projects/{project_id}/snapshots/...`
- 日志：`projects/{project_id}/logs/...`
- 导出：`projects/{project_id}/exports/...`

这样做的好处是：

- 路径就能直接表达项目边界
- 数据表和 Storage policy 更容易对齐
- 后续即使拆 bucket，也能保留一致的路径语义

## 云端迁移后的配置变更

`sprout` 完成全面云端迁移（2026-04-08）后，以下配置已调整：

- `config/supabase_config.json` 中 `timeout_seconds` 从 `30` 调整为 `300`，以适配大文件上传（视频等）
- `storage.py` 新增 TUS 分片上传支持，超过 20MB 的文件自动分片上传，无需调用方额外处理
- `sprout-projects` bucket 的 `file_size_limit` 调整为 500MB
