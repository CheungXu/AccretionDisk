# Sprout 登录与项目管理计划

> **注意：** 本文档为历史规划记录。其中引用的本地注册表 (`registry.py`) 和云端导入服务 (`cloud_import_service.py`) 已在云端迁移中删除，实施详情见 `doc/20260408/sprout-cloud-migration-complete.md`。

## 目标

在现有 `sprout` 后端与 Supabase 二期底座基础上，补齐一套最小可用的登录与项目管理体验：

- 首页从工作台改为登录页
- 登录成功后跳转到现有项目管理工作台
- 使用 `HttpOnly Cookie` 保存登录态
- 先创建一个临时 `admin` 用户，后续由你自行修改密码
- 使用 `data/sprout/node_test_case` 导入到 `admin` 用户名下的云端数据中
- 完成一次从登录到项目管理页面的真实联调

## 已确认约束

- 登录态方案：`HttpOnly Cookie`
- `admin` 账号：本轮由我先创建，后续你再修改密码
- 当前不提交、不推远程
- 保持当前整体项目结构，不做大范围重构

## 现状判断

当前 Web 首页就是工作台页面，而不是独立登录页。

首页默认入口：

- `agents/sprout/service/http_server.py`
- `agents/sprout/web/pages/index.html`
- `agents/sprout/web/pages/index.js`

当前 API 还没有用户上下文通道：

- `agents/sprout/service/http_api.py` 的 `handle_request()` 目前只接收 `method`、`raw_path`、`body`
- 若要做 Cookie 登录态，必须把请求 headers 或解析后的 session 信息从 `http_server.py` 传入 `http_api.py`

当前 `node_test_case` 的本地导入链路已经存在：

- `agents/sprout/service/project_service.py`
- `agents/sprout/service/registry.py`
- `data/sprout/node_test_case`

## 代码改造方案

### 1. 登录态与认证入口

在以下文件之间增加用户上下文传递：

- `agents/sprout/service/http_api.py`
- `agents/sprout/service/http_server.py`

改造方向：

- 扩展 `handle_request()` 的签名，允许接收请求 headers
- 在 `http_server.py` 中读取 `Cookie`
- 在 API 层增加统一的 session 解析与鉴权入口
- 对 `/api/login`、`/api/logout`、`/api/session` 增加匿名开放
- 对项目管理相关 `/api/projects*`、运行、版本、媒体等接口增加登录校验

### 2. Web 页面拆分

新增独立登录页，而不是直接把现有工作台硬改成登录页。

预计新增：

- `agents/sprout/web/pages/login.html`
- `agents/sprout/web/pages/login.js`

并调整：

- `agents/sprout/service/http_server.py`
  - 根路径 `/` 默认指向登录页
- `agents/sprout/web/pages/index.js`
  - 进入工作台前先调用 `/api/session`
  - 未登录则跳回登录页

这样可以保留现有 `index.html` 作为项目管理工作台，减少回归风险。

### 3. 会话服务封装

在 `sprout` 服务层补一个桥接 Supabase Auth 的轻量服务。

预计新增：

- `agents/sprout/service/auth_service.py`

职责：

- 使用现有 `module/database/Supabase/auth.py`
- 登录时创建会话并写 Cookie
- 从 Cookie 中解析 access token
- 查询当前用户
- 登出时清 Cookie

Cookie 策略建议：

- `HttpOnly`
- `Path=/`
- `SameSite=Lax`
- 本地开发阶段先不开 `Secure`

## 云端数据接入方案

### 1. 先创建临时 admin 用户

通过现有 Supabase Auth/Admin 能力：

- 使用 `service_role_key` 创建一个临时 `admin` 用户
- 把用户资料补到 `profiles`
- 项目级权限上，让该账号在导入项目里成为 `owner`

密码策略：

- 本轮创建时使用临时强密码
- 完成联调后由你自行修改

### 2. 导入 `node_test_case` 到 admin 名下

本轮不推翻现有本地导入，而是增加一条“导入本地项目到云端”的桥接流程。

预计在 `agents/sprout/service/project_service.py` 或新的云端导入辅助服务中增加：

- 读取 `data/sprout/node_test_case`
- 解析本地 bundle / manifest / 版本 / 运行记录 / 资产
- 调用：
  - `SproutCloudProjectStore`
  - `SproutCloudAssetStore`
  - `SproutCloudVersionStore`
  - `SproutCloudRunStore`
- 给 admin 用户写入 `project_members.role = owner`

本轮优先保证以下内容能完成真实导入：

- `projects`
- `project_members`
- `project_snapshots`
- `project_versions`
- `project_runs`
- `project_assets`

## Web 功能联调范围

本轮联调至少覆盖：

1. 打开 `/` 进入登录页
2. 使用临时 admin 账号登录成功
3. 跳转到工作台页
4. `/api/session` 返回当前用户信息
5. 项目列表中能看到导入的 `node_test_case`
6. 进入项目详情页后，项目、版本、节点、运行记录正常展示
7. 退出登录后，重新访问工作台会被重定向回登录页

如有余量，再补一轮：

- 媒体访问接口在登录态下是否正常
- 非登录态访问 `/api/projects` 是否返回 `401` 或 `403`

## 受影响文件

### 后端

- `agents/sprout/service/http_api.py`
- `agents/sprout/service/http_server.py`
- `agents/sprout/service/project_service.py`
- `agents/sprout/service/__init__.py`
- 新增 `agents/sprout/service/auth_service.py`
- 可能新增一个项目云端导入辅助服务，例如 `cloud_import_service.py`

### 前端

- `agents/sprout/web/pages/index.html`
- `agents/sprout/web/pages/index.js`
- 新增 `agents/sprout/web/pages/login.html`
- 新增 `agents/sprout/web/pages/login.js`
- `agents/sprout/web/services/api.js`

### Supabase 模块

- `module/database/Supabase/auth.py`
  - 若需要补创建 admin 用户的管理接口
- 复用现有：
  - `module/database/Supabase/project_tables.py`
  - `module/database/Supabase/storage.py`

### 文档

- `agents/sprout/readme.md`
- `agents/sprout/web/readme.md`
- `module/database/Supabase/readme.md`
- 新增 `doc/20260408/` 下本轮登录改造记录
- 视结果更新 `wiki/supabase/` 或 `wiki/sprout/`

## 验收标准

本轮完成后，应满足：

- 根路径打开的是登录页，不再直接进入工作台
- 登录成功后可进入项目管理页
- 登录态使用 `HttpOnly Cookie`，前端不直接保存 access token
- 成功创建一个临时 admin 账号
- `data/sprout/node_test_case` 已导入到该 admin 名下的云端项目数据
- admin 登录后能在 Web 端看到并打开该项目
- 未登录用户无法直接访问项目管理 API

## 风险提示

主要风险：

- 当前 API 结构原本没有 headers / session 通道，改造点集中在 `http_server.py` 和 `http_api.py`
- 现有工作台默认假设匿名可读项目，改成登录后需要同步调整前端加载流程
- `node_test_case` 的导入需要明确区分“本地注册表”和“云端导入”，避免混淆来源
- admin 用户创建逻辑如果直接写死在页面流程里，后续维护会不方便，因此更适合落服务层
