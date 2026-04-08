# Sprout Web 登录与会话策略

## 适用场景

当一个工作台同时具备：

- 自己的后端 API
- 自己的静态页面入口
- 基于 Supabase Auth 的登录能力

推荐把登录态收敛到后端维护，而不是让前端自己长期持有 token。

## 当前策略

`sprout` 当前采用：

- 首页为登录页
- 登录成功后跳转工作台
- 会话由后端写入 `HttpOnly Cookie`
- 前端通过 `/api/session` 判断是否已登录

## 为什么使用 HttpOnly Cookie

对当前这种“静态页 + 自建后端 API”的结构来说，Cookie 有几个优势：

- 前端不需要保存 access token
- 浏览器会自动带 Cookie 调用同域 `/api/*`
- 安全性比前端自己存 token 更好
- 登录页、工作台页、节点页都能复用同一套会话判断

## 页面分工

当前建议：

- `/`：登录页
- `/pages/index.html`：项目管理页
- `/pages/node.html`：节点详情页

这样可以把“登录入口”和“业务工作台”分开，避免首页承担过多职责。

## 后端分工

当前建议把职责拆成：

- `auth_service.py`：登录、登出、Cookie、session
- `http_server.py`：透传请求头、决定静态入口
- `http_api.py`：统一鉴权、路由分发

## 注意事项

- 未登录时，API 应返回 `401`
- 页面初始化时要先调用 `/api/session`
- 节点详情页不要绕过登录判断
- 登出时不仅要清 Cookie，也应尽量通知 Supabase 结束当前会话
