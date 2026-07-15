# 04 · JWT 校验实装 + user 隔离

- **Status**: proposed
- **Type**: bug
- **Priority**: 上线阻塞
- **Blocked by**: 02
- **Blocks**: 06, 07, 09
- **Est**: S-M
- **Parent PRD**: docs/PRD-V5.md §User Stories #48, #49

## What to build

当前 auth 是装饰品：JWT 会颁但没端点校验；`user_id` 走 query 参数任填任用。修。

- `backend/app/api/auth.py`：`exp` 改用 int Unix timestamp（不是 ISO string）
- `backend/app/core/config.py`：`JWT_SECRET` 无 env 时**启动失败**（不 fallback random；生产必须显式配）；开发用 `.env.example` 提供 dev 值
- 新建 `backend/app/deps.py`：`get_current_user()` FastAPI Dependency，从 `Authorization: Bearer <token>` 拿 JWT，验签 + 验 exp + 载入 user
- 所有 `/api/projects/*`、`/api/workspace/*`、`/api/memory/*` 端点声明 `current_user: User = Depends(get_current_user)`
- 服务端**忽略客户端传的 user_id**，一律用 `current_user.id`
- 数据库查询加 owner 校验（`WHERE project.user_id = current_user.id`）
- 前端 axios 拦截器自动加 `Authorization` header（`useApiClient` composable）

## Acceptance criteria

- [ ] 启动时 `JWT_SECRET` 未设 → 明确报错退出（不 fallback）
- [ ] `/api/projects/list` 无 token → 401
- [ ] `/api/projects/list` 错 token → 401
- [ ] `/api/projects/list` 对的 token 拿的项目**只属于 token 里的 user**
- [ ] user A 尝试 `DELETE /api/projects/{userB_project_id}` → 404 或 403（不泄露存在性）
- [ ] 前端登录后自动带 Authorization，无 token 时 redirect 到 /login
- [ ] `backend/tests/test_auth.py` 覆盖以上场景

## Notes

- 从 API 移除所有 `user_id: int = Query(...)` 参数（一律从 token 拿）
- 前端 `Dashboard.vue` / `useWorkspace.ts` 里 `?user_id=...` 调用要相应改
- 保留 `.env.example`，明示需要哪些 secret
