# Supabase 最小角色模型与 RBAC 演进建议

## 适用场景

当项目已经从“单人本地工作流”进入“多用户项目协作”，但又不想一开始就把权限系统做得过重时，推荐先从项目级最小角色模型开始。

`sprout` 当前就是这种情况：

- 资源边界天然以项目为中心
- 核心对象包括项目、版本、运行记录、资产和快照
- 当前最需要解决的是“谁能看、谁能改、谁能重跑、谁能管成员”

## 最小角色模型

当前推荐三档角色：

- `owner`
- `editor`
- `viewer`

### `owner`

适合：

- 管项目
- 管成员
- 切换版本
- 删项目

### `editor`

适合：

- 改项目内容
- 触发工作流
- 上传资产
- 生成版本和运行记录

### `viewer`

适合：

- 只读查看项目
- 查看版本、日志、产物

## 为什么先不直接上 RBAC

完整 RBAC 的优点是灵活，但它会同时带来：

- 更多表
- 更复杂的 RLS
- 更重的模块与 skill 更新成本

对于 `sprout` 当前阶段，先把项目协作和项目隔离跑通更重要。

## 预留升级路径

虽然当前不建：

- `roles`
- `permissions`
- `role_permissions`

但建议提前统一动作语义，例如：

- `project.read`
- `project.update`
- `project.delete`
- `member.manage`
- `version.activate`
- `run.retry`
- `asset.upload`
- `asset.delete`

这样未来升级到 RBAC 时，可以：

- 保留现有表结构主体
- 替换角色判断来源
- 继续沿用已有动作命名

## 与 RLS 的关系

当前推荐把 `project_members` 作为统一授权中心。

也就是说：

- 数据表的访问策略围绕 `project_members`
- Storage 的访问策略也围绕 `project_members`

这样可以确保：

- 数据库和 Storage 的权限边界一致
- 项目成员关系是唯一事实来源

## 对 `sprout` 的建议

当前最稳的落法是：

1. 先用 `owner / editor / viewer`
2. 先把 `projects`、`project_members`、`project_versions`、`project_runs`、`project_assets`、`project_snapshots` 跑通
3. 等工作台和多人协作稳定以后，再评估是否升级到 RBAC
