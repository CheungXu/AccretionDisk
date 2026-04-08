# Sprout 登录页与 admin 联调记录

## 工作背景

当前 `sprout` 工作台原本默认打开首页即进入项目管理页，并且后端接口默认按本地注册表工作，不区分登录用户。

本轮目标是：

- 将首页改为登录页
- 登录成功后跳转到项目管理工作台
- 使用 `HttpOnly Cookie` 保存登录态
- 引入临时 `admin` 账号
- 用 `data/sprout/node_test_case` 做云端项目导入联调

## 本次实现范围

本次已经完成：

- 后端 API 增加登录态解析通道
- 增加 `/api/login`、`/api/logout`、`/api/session`
- 项目管理相关接口增加登录校验
- 首页切换为登录页
- 新增登录页 `login.html` / `login.js`
- 工作台页与节点页增加 session 校验和登出入口
- 新增 `SproutAuthService`
- 新增 `SproutCloudImportService`
- `project_service` 增加基于当前用户的云端项目查询入口

## 当前状态

当前代码层已经支持：

- 登录页入口
- Cookie 会话
- 基于当前用户列出项目
- 导入本地项目到云端表与 Storage 的桥接逻辑

当前仍未完成的真实联调部分：

- 远端 Supabase 二期表结构和 RLS 还没有真正执行到 Workspace
- 临时 admin 用户还没有在远端实际创建成功
- `node_test_case` 还没有真正导入到远端数据库
- 浏览器端的整链路联调还需要基于真实远端表继续验证

## 当前阻塞

当前主要阻塞不是代码，而是远端数据库初始化通道：

- 本地没有 Supabase CLI
- 仓库里没有数据库连接串
- 现有 `service_role_key` 不足以直接执行建表 SQL
- 若要真正创建表和 policy，需要：
  - 控制台 SQL Editor
  - 或 Supabase Management API token
  - 或数据库直连信息

## 已采取措施

为了让后续联调能快速继续，本轮已经先把以下基础打好：

- 数据库结构参考 SQL 已有
- RLS 参考 SQL 已有
- admin 创建服务已补
- 登录 Cookie 服务已补
- 登录页与工作台跳转已补
- 项目云端导入服务已补
- 本地回归测试已通过

## 后续事项

- 解决远端表结构创建通道
- 创建临时 admin 用户
- 导入 `node_test_case` 到 admin 名下
- 启动本地 Web 服务
- 用浏览器完成登录、跳转、项目查看、节点查看与登出联调
