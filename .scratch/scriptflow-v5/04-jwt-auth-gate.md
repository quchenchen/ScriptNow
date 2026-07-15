# 04 · JWT 校验实装 + user 隔离

- **Status**: done
- **Type**: bug
- **Priority**: 上线阻塞
- **Blocked by**: 02
- **Blocks**: 06, 07, 09
- **Est**: S-M
- **Parent PRD**: docs/PRD-V5.md §User Stories #48, #49

## What to build

当前 auth 是装饰品：JWT 会颁但没端点校验；`user_id` 走 query 参数任填任用。修。

- `backend/app/api/auth.py`：`exp` 改用 int Unix timestamp（不是 ISO string）
- 新建 `backend/app/config.py`（pydantic-settings）：`JWT_SECRET` 无 env 时**启动失败**（不 fallback random；生产必须显式配）
- 新建 `backend/app/security.py`：hash_password / verify_password / create_access_token / decode_access_token / InvalidTokenError
- 新建 `backend/app/deps.py`：`get_current_user()` + `get_owned_project()` FastAPI Dependencies
- 所有 `/api/projects/*`、`/api/workspace/*`、`/api/memory/*` 端点用 `CurrentUser` / `OwnedProject`
- 服务端**忽略客户端传的 user_id**，一律用 `current_user["id"]`
- 数据库查询加 owner 校验（走 `get_owned_project` 依赖，非 owner 返 404 不泄露存在性）
- 前端 axios 拦截器自动加 `Authorization` header

## Acceptance criteria

- [x] 启动时 `JWT_SECRET` 未设 → 明确报错退出（不 fallback）— pydantic-settings 用 required field, `test_settings_rejects_missing_jwt_secret` 覆盖
- [x] `/api/projects/list` 无 token → 401（`test_projects_list_without_token_returns_401`）
- [x] `/api/projects/list` 错 token → 401（`test_projects_list_with_bad_token_returns_401`）
- [x] `/api/projects/list` 对的 token 拿的项目**只属于 token 里的 user**（`test_projects_list_returns_only_own_projects`）
- [x] user A 尝试 `DELETE /api/projects/{userB_project_id}` → 404（`test_delete_other_users_project_returns_404`）
- [x] user A `GET` user B 的 project → 404（`test_get_other_users_project_returns_404`）
- [x] 前端登录后自动带 Authorization（api.ts request interceptor 从 `localStorage.scriptflow_user.token` 读，装载到 `api` 实例和全局 `axios`）；无 token / 401 → 清 session + reload → LoginPage
- [x] Token exp 是 int Unix seconds（PyJWT 原生验签），过期 → 401；篡改 → 401（`test_expired_token_is_rejected` + `test_tampered_token_is_rejected`）
- [x] `pytest -v` — 19 passed（原有 5 + 本 slice 14）

## Notes

- 移除了 API 里所有 `user_id: int = Query(...)` 参数（一律从 token 拿）
- 前端 `api.ts` 的 `listProjects()` 不再传 user_id；useWorkspace.ts 直接调 axios 的部分被全局 axios interceptor 兜住
- `.env.example` 提供 dev 用 JWT_SECRET
- **遗留**：`app/core/config.py`（旧 Settings）保持不动作为 backward-compat；新的 pydantic-settings-based `Settings` 在 `app/config.py`。收敛这两个文件留给独立小 slice（不阻塞任何 issue）
- **遗留**：`ruff check app/` 报 26 个错误（都在 service/agent 老代码，不在本 slice 触碰的文件里），留给 #05 dead-code cleanup slice
