# Supabase Python 模块计划

## 目标

在 `AccretionDisk/module/database/Supabase/` 下建设一个可复用的 Python 模块，供不同项目统一接入 Supabase。

第一阶段范围控制为通用底层能力：

- 配置读取
- 客户端初始化
- `Auth / Session / User` 基础封装

本阶段先不进入 `sprout` 的项目、成员、权限业务表设计。

## 已确认约束

- 实现语言：`Python`
- 第一阶段范围：到 `client + auth`
- 敏感配置：`config/supabase_key.json`
- 非敏感配置：`config/supabase_config.json`
- 除 `readme` 外，还要同步更新 `doc/` 与 `wiki/`

## 本轮计划产物

预计会新增或更新以下内容：

- `module/database/Supabase/__init__.py`
- `module/database/Supabase/config.py`
- `module/database/Supabase/client.py`
- `module/database/Supabase/auth.py`
- `module/database/Supabase/readme.md`
- `module/database/Supabase/plan.md`
- `config/supabase_key.json`
- `config/supabase_config.json`
- `.gitignore`
- `doc/20260408/supabase-python-auth-module.md`
- `wiki/supabase/configuration.md`

## 配置文件策略

这次不是直接填正式参数，而是先建立两个配置模板，你后续再补真实信息。

### 1. 私密配置模板

文件：

- `config/supabase_key.json`

职责：

- 保存敏感参数
- 本地使用
- 加入 `.gitignore`

模板字段初步约定：

```json
{
  "url": "请填写 Supabase 项目 URL",
  "anon_key": "请填写匿名访问密钥",
  "service_role_key": "请填写服务端管理密钥"
}
```

### 2. 公共配置模板

文件：

- `config/supabase_config.json`

职责：

- 保存非敏感默认参数
- 可以提交到仓库
- 供不同项目复用统一默认行为

模板字段初步约定：

```json
{
  "project_name": "请填写项目标识",
  "schema": "public",
  "timeout_seconds": 30,
  "auth": {
    "auto_refresh_token": true,
    "persist_session": false
  }
}
```

## 模块设计

### 1. 配置层

参考现有 `module/api/seed/config.py` 的做法，统一实现：

- 根目录定位
- JSON 文件读取
- 私密配置与公共配置分离加载
- 支持显式传入配置路径覆盖默认路径

计划提供：

- `load_supabase_secret()`
- `load_supabase_section(section_name)`
- `load_json_file()`

### 2. 客户端层

在 `client.py` 中统一收口 Supabase 客户端初始化，避免上层业务重复散落：

- `create_anon_client()`
- `create_service_client()`

设计原则：

- 普通业务默认走 `anon` 客户端
- 管理能力单独走 `service_role` 客户端
- 通过命名显式区分权限上下文

### 3. Auth 封装层

在 `auth.py` 中先做通用认证能力：

- 邮箱注册
- 邮箱登录
- 登出
- 刷新 session
- 获取当前用户
- 基于 `service_role_key` 的管理侧用户能力

说明：

- 本阶段只做通用账号能力
- 不直接耦合 `sprout` 的项目表和权限表

## 文档更新策略

除了模块内 `readme`，还会按仓库规则同步补两类文档。

### 1. `doc/`

面向项目推进与阶段记录，计划新增：

- `doc/20260408/supabase-python-auth-module.md`

计划记录内容：

- 本轮工作背景
- 模块范围与边界
- 已完成内容
- 配置模板策略
- 风险和后续事项

### 2. `wiki/`

面向跨项目复用知识，计划新增：

- `wiki/supabase/configuration.md`

计划沉淀内容：

- Supabase 模块的配置拆分原则
- `anon_key` 与 `service_role_key` 的职责区别
- Python 项目中可复用的接入方式
- 后续扩展到 RBAC / RLS 时的演进建议

## `.gitignore` 处理

会补充：

- `config/supabase_key.json`

保留公共配置文件 `config/supabase_config.json` 可提交。

## 第一阶段不做

以下内容放到下一阶段：

- `sprout` 项目表设计
- 成员关系与角色权限模型
- RLS 策略 SQL
- 前端页面接入
- Storage / Realtime / Edge Functions

## 实施顺序

1. 建立 `module/database/Supabase/` 目录与基础文件。
2. 建立两个配置模板文件。
3. 更新 `.gitignore`，忽略 `config/supabase_key.json`。
4. 完成配置读取层。
5. 完成客户端初始化封装。
6. 完成 `Auth / Session / User` 基础封装。
7. 补充 `readme`、`doc`、`wiki`。

## 验收标准

完成后应满足：

- 可以通过统一模块创建 `anon` / `service` 客户端
- 代码中不硬编码 Supabase 密钥
- 两个配置文件先以模板形式落地
- `supabase_key.json` 被忽略，不进入版本控制
- `supabase_config.json` 可作为公共默认配置提交
- `readme`、`doc`、`wiki` 三类文档都完成对应更新
