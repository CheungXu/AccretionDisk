# Supabase Python Auth 模块工作记录

## 工作背景

本轮工作的目标是为 `AccretionDisk` 补一个可跨项目复用的 Supabase Python 模块，优先解决账号认证相关的底层接入问题，方便后续 `sprout` 等项目统一复用。

## 本次范围

本次只覆盖第一阶段通用底座：

- Supabase 配置读取
- `anon` / `service_role` 客户端初始化
- `Auth / Session / User` 基础封装

本轮暂不进入：

- 项目表设计
- 成员关系设计
- RBAC / RLS 权限规则
- 前端页面接入

## 本次进展

本次已完成：

- 新建 `module/database/Supabase/` 模块目录
- 补充 `module/database/__init__.py`
- 新增 `config.py`，统一读取私密配置与公共配置
- 新增 `client.py`，封装标准库版 Supabase REST 客户端
- 新增 `auth.py`，封装注册、登录、登出、刷新 session、获取当前用户、管理侧用户查询
- 新增模块级 `readme.md`
- 新建 `config/supabase_key.json` 模板
- 新建 `config/supabase_config.json` 模板
- 更新 `.gitignore`，忽略 `config/supabase_key.json`
- 补充 `wiki/supabase/configuration.md`

## 当前状态

当前模块已经具备以下基础能力：

- 本地模板配置已到位，后续可直接补真实 Supabase 参数
- 业务代码可统一创建 `anon` 客户端与 `service` 客户端
- 普通用户认证流程可复用统一封装
- 服务端管理侧用户查询能力已有基础入口

当前实现方式为：

- 不额外引入第三方 SDK
- 使用 Python 标准库 `urllib` 发起请求
- 通过 `config/` 管理默认参数与本地密钥

## 配置策略

当前配置已按职责拆分：

- `config/supabase_key.json`：本地私密配置
- `config/supabase_config.json`：可提交的公共默认配置

其中：

- `supabase_key.json` 先以模板形式创建，等待后续补真实值
- `supabase_config.json` 先提供默认结构，后续可按项目需要补更多非敏感参数

## 风险与问题

当前主要风险：

- 目前只覆盖认证链路，尚未进入业务表访问层
- 由于尚未接真实 Workspace，本轮还没有做联调验证
- Supabase 后续若需要 Storage、Realtime、RLS，仍需继续扩展模块

需要注意：

- `service_role_key` 权限较高，必须仅限服务端使用
- 当前 session 持久化仅为进程内缓存，不涉及磁盘持久化

## 已采取措施

为降低后续接入成本，本轮已做：

- 敏感配置与公共配置分离
- 模块职责边界先收敛到认证底层
- 统一客户端工厂，避免上层业务重复初始化
- 文档、工作记录、知识库同步补齐

## 对项目的影响

正面影响：

- `AccretionDisk` 现在具备了独立的数据库接入层雏形
- 后续 `sprout` 接入 Supabase 时可以直接复用底层模块
- 账号体系相关工作不需要从零开始重复封装

待关注影响：

- 若后续权限模型复杂，需要尽快补第二阶段的表结构与 RLS 设计
- 若多项目同时接入，需要进一步抽象业务侧服务层边界

## 后续事项

- 补充真实的 `supabase_key.json` 信息
- 根据实际 Workspace 配置调整 `supabase_config.json`
- 用真实账号链路验证注册、登录、登出、刷新 session
- 进入第二阶段：表结构、成员关系、权限模型、RLS 策略
